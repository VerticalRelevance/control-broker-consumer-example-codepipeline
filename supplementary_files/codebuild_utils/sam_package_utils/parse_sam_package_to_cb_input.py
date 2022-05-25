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

bucket = os.environ['TFPlanBucket']
print(f'bucket:\n{bucket}\n{type(bucket)}')

path = f'{os.environ["CODEBUILD_SRC_DIR"]}/tfplan.json'

build_id = os.environ["CODEBUILD_BUILD_ID"]

key = f'{codepipeline_execution_id}/sam_packaged_template.json'

item = {
    'Bucket':bucket,
    'Key':key,
    'Path':path,
}

upload_file(
    bucket = item['Bucket'],
    key = item['Key'],
    file_path = item['Path']
)

codebuild_to_sfn_artifact = {
    "CodeBuildToSfnArtifact": {
        "CodePipelineExecutionId":codepipeline_execution_id,
        "CodeBuildInputs":[item],
        "Context": {
            "EnvironmentEvaluation":"Prod",
            "PipelineOwnershipMetadata": json.loads(os.environ["PipelineOwnershipMetadata"]),
        }
    }
}

with open(codebuild_to_sfn_artifact_file,'w') as f:
    json.dump(codebuild_to_sfn_artifact,f,indent=2)
    