import io
import os
import plistlib
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from enum import Enum
from io import BytesIO
from uuid import uuid4
from typing import Optional

from androguard.core.bytecodes.apk import APK
from pydantic import BaseModel, field_validator

from app_distribution_server.errors import InvalidFileTypeError
from app_distribution_server.logger import logger


class Platform(str, Enum):
    ios = "ios"
    android = "android"

    @property
    def display_name(self):
        match = {
            self.ios: "iOS",
            self.android: "Android",
        }
        return match[self]

    @property
    def app_file_name(self):
        match = {
            self.ios: "app.ipa",
            self.android: "app.apk",
        }
        return match[self]


class LegacyAppInfo(BaseModel):
    """
    This was the structure used by v1.
    We keep this model unchanged in order to perform the migration from the old app_info.json fle.
    """

    app_title: str
    bundle_id: str
    bundle_version: str
    app_picture_url: Optional[str] = None
    app_description: Optional[str] = None

    @field_validator("bundle_id")
    def validate_bundle_id(cls, v):
        if not re.match(r"^[a-zA-Z0-9\.\-\_]{1,256}$", v):
            raise ValueError(
                "Bundle ID can only contain alphanumeric characters, dots, hyphens and underscores."
            )
        return v


class BuildInfo(LegacyAppInfo):
    upload_id: str
    file_size: int
    created_at: Optional[datetime]
    platform: Platform
    version_code: Optional[int] = None  # Android
    build_number: Optional[str] = None  # iOS

    @property
    def human_file_size(self) -> str:
        one_kb = 1024
        if self.file_size is None:
            return "unknown size"

        if self.file_size < one_kb:
            return f"{self.file_size}B"

        if self.file_size < one_kb**2:
            return f"{self.file_size / one_kb:.2f}KB"

        if self.file_size < one_kb**3:
            return f"{self.file_size / one_kb**2:.2f}MB"

        return f"{self.file_size / one_kb**3:.2f}GB"


def get_build_info_from_ipa(
    upload_id: str,
    ipa_file: BytesIO,
) -> BuildInfo:
    with zipfile.ZipFile(ipa_file, "r") as ipa:
        for file in ipa.namelist():
            if file.endswith(".app/Info.plist"):
                plist_file_content = ipa.read(file)

                info = plistlib.loads(plist_file_content)
                bundle_id = info.get("CFBundleIdentifier")
                app_title = info.get("CFBundleName")
                bundle_version = info.get("CFBundleShortVersionString")
                build_number = info.get("CFBundleVersion")

                if bundle_id is None or app_title is None or bundle_version is None:
                    logger.error("Failed to extract plist file information")
                    raise InvalidFileTypeError()

                return BuildInfo(
                    upload_id=upload_id,
                    platform=Platform.ios,
                    app_title=app_title,
                    bundle_id=bundle_id,
                    bundle_version=bundle_version,
                    build_number=build_number,
                    created_at=datetime.now(timezone.utc),
                    file_size=ipa_file.getbuffer().nbytes,
                )

    logger.error("Could not find plist file in bundle")
    raise InvalidFileTypeError()


def get_build_info_from_apk(
    upload_id: str,
    apk_file: BytesIO,
) -> BuildInfo:
    tempdir = tempfile.mkdtemp()
    file_name = "app.apk"
    file_path = os.path.join(tempdir, file_name)

    try:
        with open(file_path, "wb") as f:
            f.write(apk_file.read())

        apk = APK(file_path)
        app_title = apk.get_app_name()
        bundle_id = apk.get_package()
        version_code = apk.get_androidversion_code()
        version_name = apk.get_androidversion_name()

        return BuildInfo(
            upload_id=upload_id,
            platform=Platform.android,
            app_title=app_title,
            bundle_id=bundle_id,
            bundle_version=version_name,
            version_code=version_code,
            created_at=datetime.now(timezone.utc),
            file_size=apk_file.getbuffer().nbytes,
        )
    finally:
        shutil.rmtree(tempdir)


def get_build_info(
    platform: Platform,
    app_file_content: bytes,
):
    upload_id = str(uuid4())

    logger.debug(f"Obtaining build info from {upload_id!r}")

    file_contents_stream = io.BytesIO(app_file_content)

    if platform == Platform.ios:
        return get_build_info_from_ipa(
            upload_id,
            file_contents_stream,
        )

    return get_build_info_from_apk(
        upload_id,
        file_contents_stream,
    )
