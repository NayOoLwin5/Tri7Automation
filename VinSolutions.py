import time

import aiohttp
from expiringdict import ExpiringDict
from google.cloud.firestore_v1 import FieldFilter

from config import vinsolutions_setting
from daos.firebase_dao import get_firestore
from daos.phone_dao import separate_country_code
from integrations.base.Integrations import Integration
from models.LeadIntegration import LeadCampaign, LeadStatus, LeadType
from models.WebhookEvent import LeadPayload

INTEGRATION_URL = vinsolutions_setting.INTEGRATION_URL
INTEGRATION_CLIENT_ID = vinsolutions_setting.INTEGRATION_CLIENT_ID
INTEGRATION_CLIENT_SECRET = vinsolutions_setting.INTEGRATION_CLIENT_SECRET
INTEGRATION_SHOWROOM_API_KEY = vinsolutions_setting.INTEGRATION_SHOWROOM_API_KEY
INTEGRATION_LEAD_MM_API_KEY = vinsolutions_setting.INTEGRATION_LEAD_MM_API_KEY

source_cache = ExpiringDict(max_len=100, max_age_seconds=5 * 60 * 60)  # 5 hours
setup_cache = ExpiringDict(max_len=100, max_age_seconds=24 * 60 * 60)  # 24 hours
type_and_status_cache = ExpiringDict(max_len=100, max_age_seconds=24 * 60 * 60)  # 24 hours

firestore = get_firestore()


class VinSolutions(Integration):

    def __init__(self):
        super().__init__()
        self.integrationName = "VinSolutions"
        self.statuses_allowed = ["CLOSED_RO", "ACTIVE_NEW_LEAD", "SOLD_DELIVERED"]
        # optional let it empty if you want to get all types some crm only internet lead
        self.types_allowed = ["INTERNET", "WALK_IN", "PHONE", "IMPORT", "PARTS_ORDER", "SERVICE", "WEBSITE_CHAT", "WHOLESALE", "REFERRAL", "PREVIOUS_CUSTOMER"]
        self.access_token = None
        self.expires_timestamp = None

    async def get_access_token(self):
        if self.access_token and self.expires_timestamp > int(time.time()):
            return self.access_token
        url = 'https://authentication.vinsolutions.com/connect/token'

        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
        }

        data = {
            'grant_type': 'client_credentials',
            'client_id': INTEGRATION_CLIENT_ID,
            'client_secret': INTEGRATION_CLIENT_SECRET,
            'scope': 'PublicAPI'
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, data=data) as response:
                result = await response.json()
                self.access_token = result.get('access_token')
                self.expires_timestamp = int(time.time()) + result.get('expires_in') - 300
                return self.access_token

    async def integration_request(self, path=None, method='GET', data=None, is_digital_showroom=True, version="v3"):
        access_token = await self.get_access_token()

        url = f"{INTEGRATION_URL}{path}"

        headers = {
            'api_key': INTEGRATION_SHOWROOM_API_KEY if is_digital_showroom else INTEGRATION_LEAD_MM_API_KEY,
            'Authorization': f'Bearer {access_token}',
            'Accept': f'application/vnd.coxauto.{version}+json',
        }

        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, headers=headers, json=data) as response:
                result = await response.json()
                return result

    async def get_lead_sources(self, integration_id):
        if integration_id in source_cache:
            return source_cache[integration_id]

        i = 1
        sources = {}
        while True:
            leads_data = await self.integration_request(path=f'/leadSources?dealerid={integration_id}&limit=100&pagenumber={i}', version="v1")
            for x in leads_data.get('items', []):
                sources[x['leadSourceId']] = x['leadSourceName']
            i += 1
            if len(leads_data['items']) < 100:
                break

        source_cache[integration_id] = sources
        return sources

    async def get_lead_types(self, integration_id):
        return await self.integration_request(path=f'/leadTypes?dealerid={integration_id}', version="v1")

    async def get_lead_statuses(self, integration_id):
        return await self.integration_request(path=f'/leadStatuses?dealerid={integration_id}', version="v1")

    async def get_lead_info(self, integration_id, contact_id):
        contacts = await self.integration_request(path=f'/gateway/v1/contact?dealerId={integration_id}&userId=878992&contactId={contact_id}')
        if len(contacts) > 0:
            contacts_data = contacts[0]
            ContactInformation = contacts_data.get('ContactInformation', {})
            data_output = {
                "firstName": ContactInformation.get('FirstName', ''),
                "lastName": ContactInformation.get('LastName', ''),
                "email": ContactInformation['Emails'] and ContactInformation['Emails'][-1].get('EmailAddress', '').lower(),  # get first email
                "phone": ContactInformation['Phones'] and ContactInformation['Phones'][-1].get('Number', ''),  # get first phone
            }
            if not data_output['email']:
                data_output['email'] = ""
            if not data_output['phone']:
                data_output['phone'] = ""
            return data_output
        return None

    @staticmethod
    def mapping_index_array(data, index):
        return data[index - 1]

    @staticmethod
    def mapping_status(key):
        mapping_key = {
            1: LeadStatus.ACTIVE_NEW_LEAD.value,
            2: LeadStatus.ACTIVE_WAITING_FOR_PROSPECT_RESPONSE.value,
            3: LeadStatus.ACTIVE_ACTIVE_LEAD.value,
            4: LeadStatus.SOLD_ON_ORDER.value,
            6: LeadStatus.LOST_LEAD_PROCESS_COMPLETED.value,
            7: LeadStatus.BAD_BAD_OR_NO_CONTACT_INFORMATION.value,
            8: LeadStatus.BAD_PROSPECT_CLAIMS_NEVER_SUBMITTED.value,
            9: LeadStatus.BAD_UNDERAGE_PROSPECT.value,
            10: LeadStatus.BAD_DUPLICATE_LEAD.value,
            11: LeadStatus.SOLD_PENDING_FINANCE.value,
            12: LeadStatus.SOLD_DELIVERED.value,
            13: LeadStatus.LOST_DID_NOT_RESPOND.value,
            14: LeadStatus.LOST_BAD_CREDIT.value,
            15: LeadStatus.LOST_NO_AGREEMENT_REACHED.value,
            16: LeadStatus.ACTIVE_SET_APPOINTMENT.value,
            20: LeadStatus.ACTIVE_EMAIL_INBOX.value,
            21: LeadStatus.LOST_IMPORT_LEAD.value,
            22: LeadStatus.LOST_PURCHASED_SAME_BRAND_DIFFERENT_DEALER.value,
            23: LeadStatus.LOST_PURCHASED_DIFFERENT_BRAND_DIFFERENT_DEALER.value,
            24: LeadStatus.LOST_WORKING_WITH_OTHER_SALESPERSON.value,
            25: LeadStatus.LOST_REQUESTED_NO_FURTHER_CONTACT.value,
            26: LeadStatus.LOST_PURCHASED_FROM_PRIVATE_PARTY.value,
            27: LeadStatus.LOST_OUT_OF_MARKET.value,
            28: LeadStatus.BAD_DEALER_TEST_LEAD.value,
            29: LeadStatus.BAD_INCORRECT_CUSTOMER_PHONE.value,
            30: LeadStatus.BAD_NO_INTENT_TO_BUY.value,
            31: LeadStatus.BAD_INCENTIVIZED.value,
            32: LeadStatus.BAD_SHOPPING_OUT_OF_AREA.value,
            33: LeadStatus.BAD_NO_CONTACT_IN_FIVE_DAYS.value,
            34: LeadStatus.SERVICE_COMPLETE.value,
            35: LeadStatus.SERVICE_APPOINTMENT_SCHEDULED.value,
            36: LeadStatus.SERVICE_APPOINTMENT_MISSED.value,
            37: LeadStatus.OPEN_RO.value,
            38: LeadStatus.CLOSED_RO.value,
            39: LeadStatus.NON_CUSTOMER_INITIATED_LEAD.value,
            40: LeadStatus.SERVICE_APPOINTMENT_CANCELED.value,
        }
        return mapping_key.get(key, LeadStatus.ACTIVE_NEW_LEAD.value)

    @staticmethod
    def mapping_type(key):
        mapping_key = {
            1: LeadType.INTERNET.value,
            2: LeadType.WALK_IN.value,
            3: LeadType.PHONE.value,
            4: LeadType.IMPORT.value,
            5: LeadType.PARTS_ORDER.value,
            6: LeadType.SERVICE.value,
            7: LeadType.WEBSITE_CHAT.value,
            8: LeadType.WHOLESALE.value,
            9: LeadType.REFERRAL.value,
            10: LeadType.PREVIOUS_CUSTOMER.value,
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
            await self.integration_request(path=f'/gateway/v1/contact/{contact_id}', method='PUT', data=contacts_data, version="v3")

    async def update_intent(self, project_id, payload: LeadPayload):
        automation_configs = await self.get_integration_configs(project_id, self.integrationName)
        find_contact = await firestore.collection(f"{self.integrationName}{automation_configs.get('integrationID')}").where(filter=FieldFilter('externalID', '==', payload.externalID)).get()
        if len(find_contact) == 0:
            return
        contact_id = find_contact[0].id
        await self.integration_request(path=f'/gateway/v1/lead/{contact_id}', method='PUT', data={
            "UserId": int(automation_configs.get('userID')),
            "DealerId": int(automation_configs.get('integrationID')),
            "Note": payload.intent
        })

    async def setup_integration(self, project_id):
        # check if project_id already setup then skip
        if project_id not in setup_cache:
            automation_configs = await self.get_integration_configs(project_id, self.integrationName)
            fetch_source = await self.get_lead_sources(automation_configs.get('integrationID'))
            await self.set_source_allow(project_id, self.integrationName, list(fetch_source.values()))
            setup_cache[project_id] = True

        if "setup" not in type_and_status_cache:
            await self.set_type_allow(self.integrationName, self.types_allowed)
            await self.set_status_allow(self.integrationName, self.statuses_allowed)
            type_and_status_cache["setup"] = True

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
        vinsolutions = VinSolutions()
        await vinsolutions.run_by_status('CLOSED_RO')


    asyncio.run(run())
