from typing import Literal
from urllib.parse import quote
import datetime
import json
import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app_distribution_server.build_info import (
    Platform,
)
from app_distribution_server.config import (
    get_absolute_url,
)
from app_distribution_server.storage import (
    get_upload_asserted_platform,
    load_app_file,
    load_build_info,
)

router = APIRouter(tags=["App files"])

templates = Jinja2Templates(directory="templates")


@router.get(
    "/get/{upload_id}/app.plist",
    response_class=HTMLResponse,
)
async def get_item_plist(
    request: Request,
    upload_id: str,
) -> HTMLResponse:
    get_upload_asserted_platform(
        upload_id,
        expected_platform=Platform.ios,
    )

    build_info = load_build_info(upload_id)

    return templates.TemplateResponse(
        request=request,
        name="plist.xml",
        media_type="application/xml",
        context={
            "ipa_file_url": get_absolute_url(f"/get/{upload_id}/{Platform.ios.app_file_name}"),
            "app_title": build_info.app_title,
            "bundle_id": build_info.bundle_id,
            "bundle_version": build_info.bundle_version,
        },
    )


@router.get(
    "/get/{upload_id}/app.{file_type}",
    response_class=HTMLResponse,
)
async def get_app_file(
    request: Request,
    upload_id: str,
    file_type: Literal["ipa", "apk"],
) -> Response:
    expected_platform = Platform.ios if file_type == "ipa" else Platform.android
    get_upload_asserted_platform(upload_id, expected_platform=expected_platform)

    build_info = load_build_info(upload_id)
    app_file_content = load_app_file(build_info)

    created_at_prefix = (
        build_info.created_at.strftime("%Y-%m-%d_%H-%M-%S") if build_info.created_at else ""
    )
    file_name = f"{build_info.app_title} {build_info.bundle_version}{created_at_prefix}"

    # Log download event
    ip = request.client.host if hasattr(request, 'client') and request.client else request.headers.get('x-forwarded-for', 'unknown')
    log_entry = {
        "timestamp": datetime.datetime.utcnow().isoformat(),
        "bundle_id": build_info.bundle_id,
        "platform": build_info.platform.value,
        "upload_id": upload_id,
        "ip": ip
    }
    os.makedirs("logs", exist_ok=True)
    log_path = "logs/downloads.log"
    with open(log_path, "a") as f:
        f.write(json.dumps(log_entry) + "\n")
    print(f"[DEBUG] Logged download: {log_entry} to {log_path}")

    # Encode the filename for HTTP headers
    safe_filename = quote(file_name)
    content_disposition = f"attachment; filename*=UTF-8''{safe_filename}.{file_type}"

    return Response(
        content=app_file_content,
        media_type="application/octet-stream",
        headers={"Content-Disposition": content_disposition},
    )
