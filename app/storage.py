import os
import boto3
from .config import (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION,
                     S3_BUCKET, S3_PREFIX, S3_ENDPOINT_URL)

def upload_to_s3(local_path:str, object_name:str=None):
    if not S3_BUCKET:
        return None
    session = boto3.session.Session(
        aws_access_key_id=AWS_ACCESS_KEY_ID or None,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
        region_name=AWS_DEFAULT_REGION or None
    )
    s3 = session.client("s3", endpoint_url=S3_ENDPOINT_URL or None)
    object_name = object_name or os.path.basename(local_path)
    key = f"{S3_PREFIX}/{object_name}" if S3_PREFIX else object_name
    key = key.lstrip("/")
    s3.upload_file(local_path, S3_BUCKET, key, ExtraArgs={"ContentType":"application/xml"})
    return f"s3://{S3_BUCKET}/{key}"
