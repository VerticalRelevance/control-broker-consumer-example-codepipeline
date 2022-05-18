import json
import re
import os

import boto3
from botocore.exceptions import ClientError

import requests
from aws_requests_auth.boto_utils import BotoAWSRequestsAuth

s3 = boto3.client('s3')

session = boto3.session.Session()
region = session.region_name
account_id = boto3.client('sts').get_caller_identity().get('Account')

def get_host(*,full_invoke_url):
    m = re.search('https://(.*)/.*',full_invoke_url)
    return m.group(1)

def get_object(*,bucket,key):
    
    try:
        r = s3.get_object(
            Bucket = bucket,
            Key = key
        )
    except ClientError as e:
        print(f'ClientError:\nbucket:\n{bucket}\nkey:\n{key}\n{e}')
        raise
    else:
        print(f'no ClientError get_object:\nbucket:\n{bucket}\nkey:\n{key}')
        body = r['Body']
        content = json.loads(body.read().decode('utf-8'))
        return content

    
def lambda_handler(event,context):
    
    print(f'event:\n{event}\ncontext:\n{context}')
    
    full_invoke_url = os.environ.get('ApigwInvokeUrl')
    
    print(f'full_invoke_url:\n{full_invoke_url}')
    
    host = get_host(full_invoke_url=full_invoke_url)
    
    auth = BotoAWSRequestsAuth(
        aws_host= host,
        aws_region=region,
        aws_service='execute-api'
    )
    
    print(f'BotoAWSRequestsAuth:\n{auth}')
    
    input_to_be_evaluated_object = get_object(
        bucket = event['Input']['Bucket'],
        key = event['Input']['Key'],
    )
    
    cb_input_object = {
        "Context":{
            "EnvironmentEvaluation":"Prod",
            "PipelineOwnershipMetadata" : json.loads(os.environ['PipelineOwnershipMetadata']),
        },
        "Input": input_to_be_evaluated_object
    }
    
    r = requests.post(
        full_invoke_url,
        auth = auth,
        json = cb_input_object
    )
    
    print(f'headers:\n{dict(r.request.headers)}')
    
    content = json.loads(r.content)
    
    status_code = r.status_code
    
    apigw_response = {
        'StatusCode':status_code,
        'Content': content
    }
    
    print(f'apigw_response:\n{apigw_response}')
    
    class APIGWNot200Exception(Exception):
        # caught by invoking SFN
        pass
    
    if status_code != 200:
        raise APIGWNot200Exception
    else:
        return content