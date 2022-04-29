import sys
import os
import json

first_arg = sys.argv[1]
print(f'first_arg:\n{first_arg}\n{type(first_arg)}')
synth_to_sfn_input_file = first_arg

synthed_template_bucket = os.environ['SynthedTemplatesBucket']
print(f'synthed_template_bucket:\n{synthed_template_bucket}\n{type(synthed_template_bucket)}')


cdk_dir = f'{os.environ["CODEBUILD_SRC_DIR"]}/cdk.out'

pipeline_ownership_metadata = json.loads(os.environ["PipelineOwnershipMetadata"])

templates = []

for root, dirs, files in os.walk(cdk_dir):
    for filename in files:
        path = os.path.join(root, filename)
        if filename.endswith('.template.json'):
            templates.append(filename)

print(f'templates:\n{templates}\n{type(templates)}')

control_broker_consumer_inputs = {
    "ControlBrokerConsumerInputs":{
        "Bucket": synthed_template_bucket,
        "ConsumerMetadata": pipeline_ownership_metadata,
        "InputKeys":templates
    }
}

with open(synth_to_sfn_input_file,'w') as f:
    json.dump(control_broker_consumer_inputs,f,indent=2)
    