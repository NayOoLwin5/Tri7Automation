from fastapi import (
    APIRouter,
    responses,
    status,
)


from commons.celery.celery_app import celery_login
from pydantic import BaseModel

router = APIRouter(prefix="/api")

class SignupRequestBody(BaseModel):
    user_email: str
    name: str


class LoginResponse(BaseModel):
    success: bool
    message: str
    result: dict


@router.post("/login", response_model=LoginResponse)
async def login(request_body: SignupRequestBody):
    try:
        if not request_body.name or not request_body.user_email:
            return responses.JSONResponse(content={"success": False, "message": "Invalid params"}, status_code=status.HTTP_422_UNPROCESSABLE_ENTITY)

        task = celery_login.delay(request_body.name, request_body.user_email)

        return responses.JSONResponse(content={"success": True, "message": "Your request has been queued.", "result": {"task_id": task.id}}, status_code=status.HTTP_200_OK)
    except Exception as e:
        return responses.JSONResponse(content={"success": False, "message": str(e)}, status_code=status.HTTP_500_INTERNAL_SERVER_ERROR)
    

    