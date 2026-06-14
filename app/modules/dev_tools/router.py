from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from app.core.templates import templates

# include_in_schema=False — keeps these routes out of your OpenAPI docs
router = APIRouter(prefix="/dev", tags=["dev-tools"], include_in_schema=False)


@router.get("/payment-test", response_class=HTMLResponse)
async def payment_test_page(request: Request):
    return templates.TemplateResponse(
        request=request, name="test_payment.html", context={"request": request}
    )
