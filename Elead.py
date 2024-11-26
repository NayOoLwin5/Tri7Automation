import json
import time
import uuid
from datetime import datetime

import aiohttp
from aiohttp import BasicAuth
from expiringdict import ExpiringDict
from google.cloud.firestore_v1 import FieldFilter

from config import elead_setting
from daos.firebase_dao import get_firestore, commit_batches
from daos.lead_dao import get_leads_dict
from daos.phone_dao import separate_country_code
from integrations.base.Integrations import Integration
from models.Lead import LeadInfo
from models.LeadIntegration import LeadCampaign, LeadStatus, LeadType
from models.WebhookEvent import LeadPayload

INTEGRATION_URL = elead_setting.INTEGRATION_URL
INTEGRATION_CLIENT_ID = elead_setting.INTEGRATION_CLIENT_ID
INTEGRATION_CLIENT_SECRET = elead_setting.INTEGRATION_CLIENT_SECRET

source_cache = ExpiringDict(max_len=100, max_age_seconds=5 * 60 * 60)  # 5 hours
setup_cache = ExpiringDict(max_len=100, max_age_seconds=24 * 60 * 60)  # 24 hours
type_and_status_cache = ExpiringDict(max_len=100, max_age_seconds=24 * 60 * 60)  # 24 hours

firestore = get_firestore()


class Elead(Integration):

    def __init__(self):
        super().__init__()
        self.integrationName = "Elead"
        self.statuses_allowed = ["CLOSED_RO", "ACTIVE_NEW_LEAD", "SOLD_DELIVERED"]
        self.types_allowed = ["INTERNET", "WALK_IN", "PHONE", "IMPORT", "PARTS_ORDER", "SERVICE", "WEBSITE_CHAT", "WHOLESALE", "REFERRAL", "PREVIOUS_CUSTOMER"]
        self.access_token = None
        self.expires_timestamp = None

    async def get_access_token(self):
        if self.access_token and self.expires_timestamp > int(time.time()):
            return self.access_token

        url = "https://identity.fortellis.io/oauth2/aus1p1ixy7YL8cMq02p7/v1/token?grant_type=client_credentials&scope=anonymous"

        headers = {
            'Accept': 'application/json',
            'Cache-Control': 'no-cache',
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        async with aiohttp.ClientSession(auth=BasicAuth(INTEGRATION_CLIENT_ID, INTEGRATION_CLIENT_SECRET)) as session:
            async with session.post(url, headers=headers, data={}) as response:
                result = await response.json()
                self.access_token = result.get('access_token')
                self.expires_timestamp = int(time.time()) + result.get('expires_in') - 300
                return self.access_token

    async def integration_request(self, path=None, method='GET', data=None, integration_id=None):
        access_token = await self.get_access_token()

        url = f"{INTEGRATION_URL}{path}"

        headers = {
            'Request-Id': str(uuid.uuid4()),
            'Subscription-Id': integration_id,
            'Authorization': f'Bearer {access_token}',
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as response:
                result = await response.json()
                return result

    async def get_lead_sources(self, integration_id):
        if integration_id in source_cache:
            return source_cache[integration_id]

        sources = []
        up_type = set()
        leads_data = await self.integration_request(
            '/sales/v1/elead/productreferencedata/companyOpportunitySources',
            integration_id=integration_id,
        )
        for x in leads_data.get('items', []):
            sources.append(x['name'])
            up_type.add(x['upType'])
        source_cache[integration_id] = sources
        return sources

    @staticmethod
    def mapping_index_array(data, index):
        return data[index - 1]

    @staticmethod
    def mapping_status(key):
        mapping_key = {
            "New": LeadStatus.ACTIVE_NEW_LEAD.value,
            "Hot": LeadStatus.ACTIVE_ACTIVE_LEAD.value,
            "Working": LeadStatus.ACTIVE_ACTIVE_LEAD.value,
            "Appt No Show": LeadStatus.SERVICE_APPOINTMENT_MISSED.value,
            "No Phone": LeadStatus.BAD_BAD_OR_NO_CONTACT_INFORMATION.value,
            "Contact Made": LeadStatus.ACTIVE_WAITING_FOR_PROSPECT_RESPONSE.value,
            "Unsold Showroom": LeadStatus.LOST_NO_AGREEMENT_REACHED.value,
            "On Order": LeadStatus.SOLD_ON_ORDER.value,
            "First Response": LeadStatus.ACTIVE_WAITING_FOR_PROSPECT_RESPONSE.value,
            "Appointment Set": LeadStatus.ACTIVE_SET_APPOINTMENT.value,
            "Manager Review": LeadStatus.ACTIVE_WAITING_FOR_PROSPECT_RESPONSE.value,
            "Sold Deposit": LeadStatus.SOLD_PENDING_FINANCE.value,
            "Pre-Sold": LeadStatus.SOLD_PENDING_FINANCE.value,
            "SOLD - Spot": LeadStatus.SOLD_DELIVERED.value,
            "SOLD - Delivered": LeadStatus.SOLD_DELIVERED.value,
            "Order": LeadStatus.SOLD_ON_ORDER.value,
            "CRM Sold": LeadStatus.SOLD_DELIVERED.value,
            "DMS Sold": LeadStatus.SOLD_DELIVERED.value,
            "Rental": LeadStatus.LOST_OUT_OF_MARKET.value,
            "Wholesale": LeadStatus.LOST_OUT_OF_MARKET.value,
            "Fleet": LeadStatus.NON_CUSTOMER_INITIATED_LEAD.value,
            "Commercial": LeadStatus.NON_CUSTOMER_INITIATED_LEAD.value,
            "Transfer": LeadStatus.NON_CUSTOMER_INITIATED_LEAD.value,
            "Lease": LeadStatus.SOLD_PENDING_FINANCE.value,
            "Spot Sold": LeadStatus.SOLD_DELIVERED.value,
            "Delivered Sold": LeadStatus.SOLD_DELIVERED.value,
            "Bought Elsewhere": LeadStatus.LOST_PURCHASED_DIFFERENT_BRAND_DIFFERENT_DEALER.value,
            "Not In Market": LeadStatus.LOST_OUT_OF_MARKET.value,
            "Unable to Obtain Financing": LeadStatus.LOST_BAD_CREDIT.value,
            "Vehicle Not In Stock": LeadStatus.LOST_NO_AGREEMENT_REACHED.value,
            "Inactivity Clean Up": LeadStatus.LOST_DID_NOT_RESPOND.value,
            "File Import": LeadStatus.LOST_IMPORT_LEAD.value,
            "Dealership Request": LeadStatus.LOST_WORKING_WITH_OTHER_SALESPERSON.value,
            "Bad Lead": LeadStatus.BAD_NO_CONTACT_IN_FIVE_DAYS.value,
            "Non-Responsive": LeadStatus.LOST_DID_NOT_RESPOND.value,
            "Acquisition": LeadStatus.LOST_LEAD_PROCESS_COMPLETED.value,
            "Bought": LeadStatus.LOST_PURCHASED_FROM_PRIVATE_PARTY.value,
            "Lost": LeadStatus.LOST_LEAD_PROCESS_COMPLETED.value,
        }
        return mapping_key.get(key, LeadStatus.ACTIVE_NEW_LEAD.value)

    @staticmethod
    def mapping_type(key):
        mapping_key = {
            "Internet": LeadType.INTERNET.value,
            "Phone": LeadType.PHONE.value,
            "Showroom": LeadType.WALK_IN.value,
            "Campaign": LeadType.WEBSITE_CHAT.value,
            "Unknown": LeadType.UNKNOWN.value,
        }
        return mapping_key.get(key, LeadType.INTERNET.value)

    async def update_contact(self, project_id, payload: LeadPayload):
        automation_configs = await self.get_integration_configs(project_id, self.integrationName)
        find_contact = await firestore.collection(f"{self.integrationName}{automation_configs.get('integrationID')}").where(filter=FieldFilter('externalID', '==', payload.externalID)).get()
        if len(find_contact) == 0:
            return
        contact = find_contact[0].to_dict()
        contact_id = contact.get('extras', {}).get('customer_id')
        # check if contact Email, Phone already exist
        contacts = await self.integration_request(path=f'/gateway/v1/contact?dealerId={automation_configs.get("integrationID")}&userId={automation_configs.get("userID")}&contactId={contact_id}')
        if len(contacts) > 0:
            contacts_data = contacts[0]
            ContactInformation = contacts_data.get('ContactInformation', {})
            Emails = ContactInformation.get('Emails', [])
            Phones = ContactInformation.get('Phones', [])
            find_is_email_exist = Emails and any(x.get('EmailAddress', '').lower() == payload.email for x in Emails)
            find_is_phone_exist = Phones and any(x.get('Number', '') == payload.cellPhone for x in Phones)
            if find_is_email_exist and find_is_phone_exist:
                return
            if not find_is_email_exist:
                Emails.append({
                    "EmailId": 1 if len(Emails) == 0 else Emails[-1]['EmailId'] + 1,
                    "EmailType": "Personal",
                    "EmailAddress": payload.email
                })
            if not find_is_phone_exist:
                phone_number = payload.cellPhone
                if "+" in payload.cellPhone:
                    country_code, national_number = separate_country_code(payload.cellPhone)
                    phone_number = national_number

                Phones.append({
                    "PhoneId": 1 if len(Phones) == 0 else Phones[-1]['PhoneId'] + 1,
                    "PhoneType": "Mobile",
                    "Number": phone_number
                })

            contacts_data['UserId'] = int(automation_configs.get('userID'))
            contacts_data['ContactInformation'] = ContactInformation
            await self.integration_request(path=f'/gateway/v1/contact/{contact_id}', method='PUT', data=contacts_data, version="v4")

    async def update_intent(self, project_id, payload: LeadPayload):
        automation_configs = await self.get_integration_configs(project_id, self.integrationName)
        find_contact = await firestore.collection(f"{self.integrationName}{automation_configs.get('integrationID')}").where(filter=FieldFilter('externalID', '==', payload.externalID)).get()
        if len(find_contact) == 0:
            return
        opportunity_id = find_contact[0]['extras']['opportunity_id']
        await self.integration_request(path=f'/sales/v2/elead/opportunities/comment', method='POST', data={
            "opportunityId": opportunity_id,
            "comment": payload.intent
        }, integration_id=automation_configs.get('integrationID'))

    async def setup_integration(self, project_id):
        # check if project_id already setup then skip
        if project_id not in setup_cache:
            automation_configs = await self.get_integration_configs(project_id, self.integrationName)
            lead_sources = await self.get_lead_sources(automation_configs.get('integrationID'))
            await self.set_source_allow(project_id, self.integrationName, lead_sources)
            setup_cache[project_id] = True

        if "setup" not in type_and_status_cache:
            await self.set_type_allow(self.integrationName, self.types_allowed)
            await self.set_status_allow(self.integrationName, self.statuses_allowed)
            type_and_status_cache["setup"] = True

    async def create_leads(self, integration_id):
        main_dealer_id = f"{self.integrationName}{integration_id}"
        old_leads = await get_leads_dict(main_dealer_id)
        # lookup 1 day format yyyy-MM-ddTHH:mm:ss
        lookup_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 24 * 60 * 60))
        # get all opportunities
        opportunities = await self.integration_request(path=f"/sales/v2/elead/opportunities/searchDelta?dateFrom={lookup_date}&page=1&pageSize=100", integration_id=integration_id)
        opportunities_items = opportunities.get('items', [])
        bulk_leads = []
        for opportunity in opportunities_items:

            customer = opportunity.get('customer', {})
            customer_id = customer.get('id')
            opportunity_id = opportunity.get('id')
            created_utc_timestamp = datetime.strptime(opportunity['dateIn'], '%Y-%m-%dT%H:%M:%SZ').timestamp()

            if customer_id not in old_leads:
                lead = LeadInfo()
                lead.firstName = ""
                lead.lastName = ""
                lead.email = ""
                lead.cellPhone = ""
                lead.createdAt = int(created_utc_timestamp)
                lead.updatedAt = int(created_utc_timestamp)
                lead.extras = {
                    "opportunity_id": opportunity_id
                }
            else:
                lead = old_leads[customer_id]

            lead.externalID = customer_id
            lead.leadType = self.mapping_type(opportunity.get('subStatus'))
            if lead.leadStatus != self.mapping_status(opportunity.get('status')):
                lead.leadStatus = self.mapping_status(opportunity.get('status'))
                lead.updatedAt = int(time.time())

            lead.leadSource = opportunity.get('source')
            bulk_leads.append({
                "ref": firestore.collection(main_dealer_id).document(lead.externalID),
                "data": json.loads(lead.json()),
                "type": "set_merge"
            })

        if len(bulk_leads) > 0:
            await commit_batches(bulk_leads)

    async def run_by_status(self, status: str):

        integration_details = await self.get_integration(integration_name=self.integrationName)
        project_ids = integration_details.get('projectIDs', [])
        status_allowed = integration_details.get('statusAllows', [])

        # check if status not in status_allowed in db then update it
        if status not in status_allowed:
            await self.set_status_allow(integration_name=self.integrationName, statusAllows=status_allowed + [status])

        if status not in self.statuses_allowed:
            # todo: send notification to telegram
            return False

        for project_id in project_ids:
            await self.setup_integration(project_id)
            await self.create_leads(project_id)
            # get all automation tasks
            automation_tasks = await self.get_automation_tasks(project_id, self.integrationName)
            automation_configs = await self.get_integration_configs(project_id, self.integrationName)
            for automation_task in automation_tasks:
                lead_status = automation_task.get('leadStatus', [])
                lead_type = automation_task.get('leadType', [])
                lead_source = automation_task.get('leadSource', [])
                wait_time = automation_task.get('waitTime', 1)
                wait_time_unit = automation_task.get('waitTimeUnit', 'days')

                if len(lead_status) > 0 and status not in lead_status:
                    continue

                # convert wait time to seconds
                wait_second = 0
                if wait_time_unit == 'days':
                    wait_second = wait_time * 24 * 60 * 60
                elif wait_time_unit == 'hours':
                    wait_second = wait_time * 60 * 60
                elif wait_time_unit == 'minutes':
                    wait_second = wait_time * 60

                # get all leads by status
                leads_stream = (firestore.collection(f"{self.integrationName}{automation_configs.get('integrationID')}")
                                .where(filter=FieldFilter('leadStatus', '==', status))
                                .where(filter=FieldFilter('updatedAt', '!=', 0)).stream())
                async for lead in leads_stream:
                    lead_data = lead.to_dict()

                    # skip if lead type or lead source not in allowed
                    if len(lead_type) > 0 and lead_data['leadType'] not in lead_type:
                        continue

                    # skip if lead type or lead source not in allowed
                    if len(lead_source) > 0 and lead_data['leadSource'] not in lead_source:
                        continue

                    if lead_data.get('updatedAt') and lead_data.get('updatedAt') + wait_second > int(time.time()):
                        continue

                    if lead_data.get(status) and lead_data.get(status) + wait_second < int(time.time()):
                        continue

                    if lead_data['firstName'] == "":
                        customer = await self.integration_request(path=f"/sales/v1/elead/customers/{lead_data['externalID']}", integration_id=automation_configs.get('integrationID'))
                        lead_data['firstName'] = customer.get('firstName', "")
                        lead_data['lastName'] = customer.get('lastName', "")
                        lead_data["email"] = customer['emails'] and customer['emails'][-1].get('address', ''),
                        lead_data["cellPhone"] = customer['phones'] and customer['phones'][-1].get('number', ''),
                        if not lead_data['email']:
                            lead_data['email'] = ""
                        if not lead_data['cellPhone']:
                            lead_data['cellPhone'] = ""
                        # get only number
                        lead_data['cellPhone'] = lead_data['phone'].replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
                        await lead.reference.update({
                            "firstName": lead_data['firstName'],
                            "lastName": lead_data['lastName'],
                            "email": lead_data['email'],
                            "cellPhone": lead_data['cellPhone']
                        })

                    lead_model = LeadCampaign(
                        externalID=str(lead_data.get('externalID')),
                        externalStatus=str(lead_data.get('leadStatus')),
                        externalType=lead_data.get('leadType'),
                        externalSource=lead_data.get('leadSource'),
                        firstName=lead_data.get('firstName'),
                        lastName=lead_data.get('lastName'),
                        email=lead_data.get('email'),
                        cellPhone=lead_data.get('cellPhone')
                    )
                    if lead_model.email:
                        await self.create_campaign(project_id, automation_task['automationID'], lead_model)
                        await lead.reference.update({
                            lead_data['leadStatus']: int(time.time()),
                            "campaignAt": int(time.time())
                        })

                    else:
                        await lead.reference.update({
                            lead_data['leadStatus']: int(time.time())
                        })

    async def run(self, scheduler):
        scheduler.add_job(self.run_by_status, "interval", hours=1, args=[LeadStatus.ACTIVE_NEW_LEAD.value])
        scheduler.add_job(self.run_by_status, "interval", hours=1, args=[LeadStatus.CLOSED_RO.value])
        scheduler.add_job(self.run_by_status, "interval", hours=1, args=[LeadStatus.OPEN_RO.value])


if __name__ == '__main__':
    import asyncio


    async def run():
        elead = Elead()
        print(await elead.get_lead_sources("e17d08c2-5458-436b-9e3c-8b74079bfb75"))


    asyncio.run(run())
