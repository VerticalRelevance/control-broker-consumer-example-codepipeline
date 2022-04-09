import aws_cdk as core
import aws_cdk.assertions as assertions

from control_broker_codepipeline_example.control_broker_codepipeline_example_stack import ControlBrokerCodepipelineExampleStack

# example tests. To run these tests, uncomment this file along with the example
# resource in control_broker_codepipeline_example/control_broker_codepipeline_example_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = ControlBrokerCodepipelineExampleStack(app, "control-broker-codepipeline-example")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
