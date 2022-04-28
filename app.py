#!/usr/bin/env python3
import os

import aws_cdk as cdk

from control_broker_codepipeline_example.control_broker_codepipeline_example_stack import ControlBrokerCodepipelineExampleStack


app = cdk.App()
ControlBrokerCodepipelineExampleStack(app, "ControlBrokerCodepipelineExampleStack",
    env=cdk.Environment(account=os.getenv('CDK_DEFAULT_ACCOUNT'), region=os.getenv('CDK_DEFAULT_REGION')),
    control_broker_template_reader_arns=app.node.try_get_context("control-broker/template-reader-arns"),
    control_broker_sfn_invoke_arn=app.node.try_get_context("control-broker/sfn-invoke-arn"),
    control_broker_apigw_url=app.node.try_get_context("control-broker/apigw-url"),
    pipeline_ownership_metadata = {'PipelineId':'AppTeam1'}
)

app.synth()
