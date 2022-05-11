import sys
import os
import json
import uuid

# import boto3
# from botocore.exceptions import ClientError

# s3 = boto3.client('s3')

# TODO: upload all *.template.json to S3, rather than s3 sync in codebuild
import boto3
from botocore.exceptions import ClientError
s3 = boto3.client("s3")

def upload_file(bucket, key, file_path):
    try:
        r = s3.upload_file(
            file_path,
            bucket,
            key
        )
    except ClientError as e:
        print(f'ClientError:\n{e}')
        raise
    else:
        print(f'no ClientError upload_file\nbucket:\n{bucket}\nkey:\n{key}\nfile_path\n{file_path}\n')
        return True

def generate_uuid():
    return str(uuid.uuid4())

first_arg = sys.argv[1]
print(f'first_arg:\n{first_arg}\n{type(first_arg)}')
codebuild_to_sfn_artifact_file = first_arg

second_arg = sys.argv[2]
print(f'second_arg:\n{second_arg}\n{type(second_arg)}')
codepipeline_execution_id = second_arg

synthed_template_bucket = os.environ['SynthedTemplatesBucket']
print(f'synthed_template_bucket:\n{synthed_template_bucket}\n{type(synthed_template_bucket)}')


cdk_dir = f'{os.environ["CODEBUILD_SRC_DIR"]}/cdk.out'

build_id = os.environ["CODEBUILD_BUILD_ID"]

templates = []

for root, dirs, files in os.walk(cdk_dir):
    for filename in files:
        
        path = os.path.join(root, filename)
        
        if filename.endswith('.template.json'):
            
            uuid = generate_uuid()
            
            key = f'{uuid}{filename}'
            
            item = {
                'Bucket':synthed_template_bucket,
                'Key':key,
                'Path':path,
            }
            
            upload_file(
                bucket = item['Bucket'],
                key = item['Key'],
                file_path = item['Path']
            )
            
            templates.append(item)

print(f'templates:\n{templates}\n{type(templates)}')

codepipeline_context = json.loads(os.environ["PipelineOwnershipMetadata"])

    


codebuild_to_sfn_artifact = {
    "CodeBuildToSfnArtifact": {
        
        # gather all objects in s3://proposed-iac with prefix of this CodePipelineExecutionId
        
        "CodePipelineExecutionId":codepipeline_execution_id,
        
        # here's sufficient info about the objects to expect to enforce deny-by-default logic
        
        "Templates":templates
        
        # the list of their UUID keys 
    }
}

with open(codebuild_to_sfn_artifact_file,'w') as f:
    json.dump(codebuild_to_sfn_artifact,f,indent=2)
    