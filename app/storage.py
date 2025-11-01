# app/storage.py
import os
try:
    import boto3  # optional
except Exception:
    boto3 = None

from .config import (
    AWS_ACCESS_KEY_ID,
    AWS_SECRET_ACCESS_KEY,
    AWS_DEFAULT_REGION,
    S3_BUCKET,
    S3_PREFIX,
    S3_ENDPOINT_URL,
)

def upload_to_s3(local_path: str, object_name: str = None):
    """
    Încărcare opțională în S3/R2. Dacă nu e configurat (sau lipsesc pachetele),
    funcția iese lin și returnează None ca să nu pice workflow-ul.
    """
    if not S3_BUCKET:
        print("S3 disabled: S3_BUCKET missing.")
        return None
    if boto3 is None:
        print("S3 disabled: boto3 not available.")
        return None

    try:
        session = boto3.session.Session(
            aws_access_key_id=AWS_ACCESS_KEY_ID or None,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
            region_name=AWS_DEFAULT_REGION or None,
        )
        s3 = session.client("s3", endpoint_url=S3_ENDPOINT_URL or None)
        key = (object_name or os.path.basename(local_path)).lstrip("/")
        if S3_PREFIX:
            key = f"{S3_PREFIX.strip('/')}/{key}"
        s3.upload_file(local_path, S3_BUCKET, key, ExtraArgs={"ContentType": "application/xml"})
        url = f"s3://{S3_BUCKET}/{key}"
        print("Uploaded to:", url)
        return url
    except Exception as e:
        print("S3 upload skipped due to error:", repr(e))
        return None
