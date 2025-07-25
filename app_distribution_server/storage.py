import json

from fs import errors, open_fs, path
from typing import Optional

from app_distribution_server.build_info import BuildInfo, LegacyAppInfo, Platform
from app_distribution_server.config import STORAGE_URL
from app_distribution_server.errors import NotFoundError
from app_distribution_server.logger import logger

PLIST_FILE_NAME = "info.plist"
BUILD_INFO_JSON_FILE_NAME = "build_info.json"
LEGACY_BUILD_INFO_JSON_FILE_NAME = "app_info.json"
INDEXES_DIRECTORY = "_indexes"


filesystem = open_fs(STORAGE_URL, create=True)


def create_parent_directories(upload_id: str):
    filesystem.makedirs(upload_id, recreate=True)


def find_existing_upload(bundle_id: str, version_code: Optional[int] = None, build_number: Optional[str] = None) -> Optional[str]:
    for upload_id in filesystem.listdir("."):
        try:
            build_info = load_build_info(upload_id)
            if build_info.bundle_id == bundle_id:
                if version_code is not None and hasattr(build_info, 'version_code') and build_info.version_code == version_code:
                    return upload_id
                if build_number is not None and hasattr(build_info, 'build_number') and build_info.build_number == build_number:
                    return upload_id
        except Exception:
            continue
    return None


def save_upload(build_info: BuildInfo, app_file_content: bytes):
    # Remove old build with same version_code/build_number if exists
    existing_upload_id = None
    if build_info.platform == Platform.android and build_info.version_code is not None:
        existing_upload_id = find_existing_upload(build_info.bundle_id, version_code=build_info.version_code)
    elif build_info.platform == Platform.ios and build_info.build_number is not None:
        existing_upload_id = find_existing_upload(build_info.bundle_id, build_number=build_info.build_number)
    if existing_upload_id:
        delete_upload(existing_upload_id)
    create_parent_directories(build_info.upload_id)
    save_build_info(build_info)
    save_app_file(build_info, app_file_content)
    set_latest_build(build_info)


def get_upload_platform(upload_id: str) -> Optional[Platform]:
    for platform in Platform:
        if filesystem.exists(path.join(upload_id, platform.app_file_name)):
            return platform

    return None


def get_upload_asserted_platform(
    upload_id: str,
    expected_platform: Optional[Platform] = None,
) -> Platform:
    upload_platform = get_upload_platform(upload_id)

    if upload_platform is None:
        raise NotFoundError()

    if expected_platform is None:
        return upload_platform

    if upload_platform == expected_platform:
        return upload_platform

    raise NotFoundError()


def save_build_info(build_info: BuildInfo):
    upload_id = build_info.upload_id
    filepath = f"{upload_id}/{BUILD_INFO_JSON_FILE_NAME}"

    with filesystem.open(filepath, "w") as app_info_file:
        app_info_file.write(
            build_info.model_dump_json(indent=2),
        )


def load_build_info(upload_id: str, expected_platform: Optional[Platform] = None) -> BuildInfo:
    try:
        filepath = path.join(upload_id, BUILD_INFO_JSON_FILE_NAME)
        with filesystem.open(filepath, "r") as app_info_file:
            build_info_json = json.load(app_info_file)
            return BuildInfo.model_validate(build_info_json)

    except errors.ResourceNotFound:
        return migrate_legacy_app_info(upload_id)


def migrate_legacy_app_info(upload_id: str) -> BuildInfo:
    logger.info(f"Migrating legacy upload {upload_id!r} to v2")

    filepath = path.join(upload_id, LEGACY_BUILD_INFO_JSON_FILE_NAME)
    with filesystem.open(filepath, "r") as app_info_file:
        legacy_info_json = json.load(app_info_file)
        legacy_app_info = LegacyAppInfo.model_validate(legacy_info_json)

    file_size = filesystem.getsize(
        path.join(upload_id, Platform.ios.app_file_name),
    )

    build_info = BuildInfo(
        app_title=legacy_app_info.app_title,
        bundle_id=legacy_app_info.bundle_id,
        bundle_version=legacy_app_info.bundle_version,
        upload_id=upload_id,
        file_size=file_size,
        created_at=None,
        platform=Platform.ios,
    )

    save_build_info(build_info)
    logger.info(f"Successfully migrated legacy upload {upload_id!r} to v2")

    return build_info


def get_app_file_path(
    build_info: BuildInfo,
):
    return path.join(
        build_info.upload_id,
        build_info.platform.app_file_name,
    )


def save_app_file(
    build_info: BuildInfo,
    app_file: bytes,
):
    with filesystem.open(get_app_file_path(build_info), "wb+") as writable_app_file:
        writable_app_file.write(app_file)


def load_app_file(
    build_info: BuildInfo,
) -> bytes:
    with filesystem.open(get_app_file_path(build_info), "rb") as app_file:
        return app_file.read()


def delete_upload(upload_id: str):
    try:
        filesystem.removetree(upload_id)
        logger.info(f"Upload directory {upload_id!r} deleted successfully")
    except Exception as e:
        logger.error(f"Failed to delete upload directory {upload_id!r}: {e}")
        raise


def get_latest_upload_by_bundle_id_filepath(bundle_id):
    return path.join(INDEXES_DIRECTORY, "latest_upload_by_bundle_id", f"{bundle_id}.txt")


def set_latest_build(build_info: BuildInfo):
    filepath = get_latest_upload_by_bundle_id_filepath(build_info.bundle_id)
    filesystem.makedirs(path.dirname(filepath), recreate=True)

    with filesystem.open(filepath, "w") as file:
        file.write(build_info.upload_id)


def get_latest_upload_id_by_bundle_id(bundle_id: str) -> Optional[str]:
    filepath = get_latest_upload_by_bundle_id_filepath(bundle_id)

    logger.info(f"Retrieving latest upload id from bundle {bundle_id!r} ({filepath!r})")

    if not filesystem.exists(filepath):
        return None

    with filesystem.open(filepath, "r") as file:
        return file.readline().strip()


def list_builds_by_bundle_id(bundle_id: str):
    """Return a list of BuildInfo objects for all uploads with the given bundle_id, sorted by created_at descending."""
    builds = []
    for upload_id in filesystem.listdir("."):
        try:
            build_info = load_build_info(upload_id)
            if build_info.bundle_id == bundle_id:
                builds.append(build_info)
        except Exception:
            continue
    builds.sort(key=lambda b: b.created_at or 0, reverse=True)
    return builds
