#!/usr/bin/env python3
import os

import aws_cdk as cdk

from stacks.iac_pipeline_stack import ControlBrokerCodepipelineExampleStack


app = cdk.App()
ControlBrokerCodepipelineExampleStack(app, "CBConsumerCodepipeline",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    control_broker_input_reader_arns=app.node.try_get_context("control-broker/input-reader-arns"),
    control_broker_apigw_url=app.node.try_get_context("control-broker/apigw-url"),
    pipeline_ownership_metadata=app.node.try_get_context("control-broker/pipeline-ownership-metadata"),
)

app.synth()
