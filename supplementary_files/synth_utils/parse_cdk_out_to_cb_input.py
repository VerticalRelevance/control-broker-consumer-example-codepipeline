import sys
import os
import json

# import boto3
# from botocore.exceptions import ClientError

# s3 = boto3.client('s3')

# TODO: upload all *.template.json to S3, rather than s3 sync in codebuild


first_arg = sys.argv[1]
print(f'first_arg:\n{first_arg}\n{type(first_arg)}')
codebuild_to_sfn_artifact_file = first_arg

second_arg = sys.argv[2]
print(f'second_arg:\n{second_arg}\n{type(second_arg)}')
codepipeline_execution_id = second_arg

# synthed_template_bucket = os.environ['SynthedTemplatesBucket']
# print(f'synthed_template_bucket:\n{synthed_template_bucket}\n{type(synthed_template_bucket)}')


# cdk_dir = f'{os.environ["CODEBUILD_SRC_DIR"]}/cdk.out'

# build_id = os.environ["CODEBUILD_BUILD_ID"]

# pipeline_ownership_metadata = json.loads(os.environ["PipelineOwnershipMetadata"])

# templates = []

# for root, dirs, files in os.walk(cdk_dir):
#     for filename in files:
#         path = os.path.join(root, filename)
#         if filename.endswith('.template.json'):
#             templates.append(filename)

# print(f'templates:\n{templates}\n{type(templates)}')

# control_broker_consumer_inputs = {
#     "ControlBrokerConsumerInputs":{
#         "InputType":"CloudFormationTemplate",
#         "Bucket": synthed_template_bucket,
#         "InputKeys":templates,
#         "ConsumerMetadata": pipeline_ownership_metadata,
#     }
# }

codebuild_to_sfn_artifact = {
    "CodeBuildToSfnArtifact": {
        
        # gather all objects in s3://proposed-iac with prefix of this CodePipelineExecutionId
        
        "CodePipelineExecutionId":codepipeline_execution_id
        
        # here's sufficient info about the objects to expect to enforce deny-by-default logic
        
        # the list of their UUID keys 
    }
}

with open(codebuild_to_sfn_artifact_file,'w') as f:
    json.dump(codebuild_to_sfn_artifact,f,indent=2)
    