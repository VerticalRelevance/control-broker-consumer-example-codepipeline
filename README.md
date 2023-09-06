# An example Consumer of Control Broker: via CodePipeline

## Overview

[Control Broker](https://github.com/VerticalRelevance/control-broker) is a Policy as Code evaluation engine available via an API. Various Consumers can invoke this API to get evaluations of a given input against a series of policies expressed using the [Open Policy Agent](https://www.openpolicyagent.org) framework. This Policy-as-Code process codifies security and operational requirements into policy code, which in the case of OPA are written in the [Rego](https://www.openpolicyagent.org/docs/latest/policy-language/) language.

A common use case for OPA is a pre-deployment check in a Infrastructure-as-Code pipeline. 

The benefit of Policy-as-Code is that the App Team pushing this IaC template get this compliance feedback early & often.
To this end, an App Team might hit the same endpoint that their IaC pipeline will hit, to get a pre-commit compliance check, as part of the security process known as [Shifting Left](https://about.gitlab.com/topics/ci-cd/shift-left-devops/).

This repository aims to deploy a minimal Python script that invokes the Control Broker endpoint to get an evaluation on a local file:  [payload.json](./src/control_broker_consumer_example_local_dev/payload.json), and returing the response to the (`.gitignore`'d) [output.json](./src/control_broker_consumer_example_local_dev/outputs/output.json).

This `readme.md` will cover:

1. Setup the Python environment
2. Invoke the Control Broker via the Local Python Script
3. Toggle the input to test the PaC evaluation


## 1. Setup the Python Environment

### Requirements

1. A running serverless instance of Control Broker. See setup [here](https://github.com/VerticalRelevance/control-broker)
2. A development environment capable of setting up a Python virtual environment

#### Tested with

This repository was tested with a [Cloud9](https://aws.amazon.com/cloud9/) IDE.

```
uname -a # (Cloud9) Linux ip-10-0-3-28.ec2.internal 4.14.320-243.544.amzn2.x86_64 #1 SMP Tue Aug 1 21:03:08 UTC 2023 x86_64 x86_64 x86_64 GNU/Linux
python3 -V # Python 3.9.6
```

### Fetch the Control Broker Invoke Url

The CodePipeline stacks needs to know at which URL to invoke the Control Broker instance deployed in step 1.1. 

Set `CONTROL_BROKER_STACK_NAME` in [main.py](./src/control_broker_consumer_example_local_dev/main.py)

For Python environment setup, consider: 

```bash
cat >> ~/.bashrc << EOF

alias ve='python3 -m venv venv'
alias ae='deactivate &> /dev/null; source ./venv/bin/activate'
alias pu='python3 -m pip install -U pip setuptools wheel'
alias pit='python3 -m pip install pip-tools'
alias pc='pip-compile'
alias ps='pip-sync'
alias start='ve && ae && pu && pit'
EOF
exec $SHELL
start
pc & ps
```


## 2. Invoke the Control Broker API


Let's examine our input and the policy against which it is being evaluated.

Here's our `payload.json`, which contains a CloudFormation template:

```json
{
    "Resources": {
        "MyQueue": {
            "Type": "AWS::SQS::Queue",
            "Properties": {
                "QueueName":"MyQueue",
                "ContentBasedDeduplication": true
            }
        }
    }
}
```

This [OPA policy](https://github.com/VerticalRelevance/control-broker-module-private/blob/cb-core/supplementary_files/policy_as_code/python/opa_policies/cloudformation/AWS--SQS--Queue__cfn01__dedup.rego) performs a simple operational check on that CloudFormation template. It applies to resources of type "AWS::SQS::Queue", and requires that `ContentBasedDeduplication` be `true`.

Consider loading the CloudFormation template and the OPA policy into the [Rego Playground](https://play.openpolicyagent.org/p/4rMvYQH7La) and running `Evaluate`. Toggle the `ContentBasedDeduplication` field from `true` to `false` to see how it affects the evaluation's `allow` decision.

When we run our local evaluation, we expect the initial `allow` result to be `true`.

```bash
python3 src/control_broker_consumer_example_local_dev/main.py
```

Check the response in [output.json](./src/control_broker_consumer_example_local_dev/outputs/output.json) to confirm.


Now let's toggle `ContentBasedDeduplication` to be `false` in our CloudFormation template [input.json](./supplementary_files/pipeline_inputs/CloudFormation/input.json) and save the edited file.

When re re-run, we expect the `allow` result to be `false`.

For a complete list of example Consumers of Control Broker, including a CodePipeline implementation of the IaC pipeline referenced above, see [here](https://github.com/VerticalRelevance/control-broker)

## cdk.json

add hard-coded value from `control-broker` deployment output
```
{
    "control-broker/apigw-url":"MY_URL"
}
```