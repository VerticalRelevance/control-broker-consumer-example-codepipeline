import os
import json
from typing import List
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_codebuild,
    aws_codecommit,
    aws_codepipeline,
    aws_codepipeline_actions,
    aws_iam,
    aws_lambda,
    aws_dynamodb,
    aws_s3,
    aws_s3_deployment,
    aws_stepfunctions,
    aws_logs,
    aws_events,
    aws_sqs,
    aws_lambda_python_alpha, #experimental
)
from constructs import Construct


class ControlBrokerCodepipelineExampleStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        pipeline_ownership_metadata:dict,
        control_broker_apigw_url:str,
        source_iac:str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.pipeline_ownership_metadata = pipeline_ownership_metadata
        self.control_broker_apigw_url = control_broker_apigw_url
        self.source_iac = source_iac
        
        self.layers = {
            "aws_requests_auth": aws_lambda_python_alpha.PythonLayerVersion(
                self,
                "aws_requests_auth",
                entry="./supplementary_files/lambda_layers/aws_requests_auth",
                compatible_runtimes=[
                    aws_lambda.Runtime.PYTHON_3_9
                ]
            ),
            "requests": aws_lambda_python_alpha.PythonLayerVersion(self,
                "requests",
                entry="./supplementary_files/lambda_layers/requests",
                compatible_runtimes=[
                    aws_lambda.Runtime.PYTHON_3_9
                ]
            )
        }
        
        self.source()
        if self.source_iac == "CDK":
            self.synth()
        if self.source_iac == "Terraform":
            self.plan()
        
        
        self.evaluate_wrapper_sfn_lambdas()
        self.evaluate_wrapper_sfn()
        self.pipeline()
    
    def source(self):
    
        # source

        self.repo_app_team_cdk = aws_codecommit.Repository(
            self,
            "ApplicationTeamExampleAppRepository",
            repository_name="ControlBrokerEvalEngine-ApplicationTeam-ExampleApp",
            code=aws_codecommit.Code.from_directory(
                f"./supplementary_files/application_team_example_app/{self.source_iac}", "main"
            ),
        )
        self.repo_app_team_cdk.apply_removal_policy(RemovalPolicy.DESTROY)

        self.artifact_source = aws_codepipeline.Artifact()

        self.action_source = aws_codepipeline_actions.CodeCommitSourceAction(
            action_name="CodeCommit",
            repository=self.repo_app_team_cdk,
            branch="main",
            output=self.artifact_source,
        )
        
    def synth(self):
        
        # synthed templates

        self.bucket_synthed_templates = aws_s3.Bucket(
            self,
            "SynthedTemplates",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        CfnOutput(
            self,
            "SynthedTemplatesBucket",
            value=self.bucket_synthed_templates.bucket_name,
        )

        # synth
        
        self.bucket_synth_utils = aws_s3.Bucket(
            self,
            "SynthUtils",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        aws_s3_deployment.BucketDeployment(
            self,
            "ParseCdkOutToCBInput",
            sources=[
                aws_s3_deployment.Source.asset(f"./supplementary_files/codebuild_utils/synth_utils")
            ],
            destination_bucket=self.bucket_synth_utils,
            retain_on_delete=False,
        )
        
        role_synth = aws_iam.Role(
            self,
            "Synth",
            assumed_by=aws_iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        role_synth.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:Get*",
                    "s3:List*",
                ],
                resources=[
                    self.bucket_synthed_templates.bucket_arn,
                    self.bucket_synthed_templates.arn_for_objects("*"),
                ],
            )
        )
        role_synth.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:Get*",
                    "s3:List*",
                ],
                resources=[
                    self.bucket_synth_utils.bucket_arn,
                    self.bucket_synth_utils.arn_for_objects("*"),
                ],
            )
        )
        role_synth.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "codepipeline:GetPipelineState",
                ],
                resources=["*"],
            )
        )

        self.codebuild_to_sfn_artifact_file = "control-broker-consumer-inputs.json"
            
        build_project_cdk_synth = aws_codebuild.PipelineProject(
            self,
            "CdkSynth",
            environment = aws_codebuild.BuildEnvironment(
                build_image = aws_codebuild.LinuxBuildImage.STANDARD_3_0
            ),
            role = role_synth,
            build_spec=aws_codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "on-failure": "ABORT",
                            "commands": [
                                # TODO upgrade node, v10 deprecated
                                "npm install -g typescript",
                                "npm install -g ts-node",
                                "npm install -g aws-cdk",
                                "npm install",
                                "cdk --version",
                            ],
                        },
                        "build": {
                            "on-failure": "ABORT",
                            "commands": [
                                "CODEPIPELINE_EXECUTION_ID=$(aws codepipeline get-pipeline-state --region us-east-1 --name ${CODEBUILD_INITIATOR#codepipeline/} --query 'stageStates[?actionStates[?latestExecution.externalExecutionId==`'${CODEBUILD_BUILD_ID}'`]].latestExecution.pipelineExecutionId' --output text)",
                                "echo $CODEPIPELINE_EXECUTION_ID",
                                "ls",
                                "cdk synth",
                                "ls",
                                "ls cdk.out",
                                f"aws s3 sync s3://{self.bucket_synth_utils.bucket_name} .",
                                "pip install -r requirements.txt",
                                f"python3 parse_cdk_out_to_cb_input.py {self.codebuild_to_sfn_artifact_file} $CODEPIPELINE_EXECUTION_ID",
                            ],
                        },
                    },
                    "artifacts": {
                        "files": ["**/*"],
                        "discard-paths": "no",
                        "enable-symlinks": "yes",
                    },
                }
            ),
            environment_variables={
                "SynthedTemplatesBucket": aws_codebuild.BuildEnvironmentVariable(value=self.bucket_synthed_templates.bucket_name),
                "PipelineOwnershipMetadata": aws_codebuild.BuildEnvironmentVariable(value=json.dumps(self.pipeline_ownership_metadata)),
            }
            
        )

        self.artifact_built = aws_codepipeline.Artifact()

        self.action_build = aws_codepipeline_actions.CodeBuildAction(
            action_name="CodeBuildCdkSynth",
            project=build_project_cdk_synth,
            input=self.artifact_source,
            outputs=[self.artifact_built],
        )
    
    def plan(self):
        
        # synthed templates

        self.bucket_tfplan = aws_s3.Bucket(
            self,
            "TFPlan",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        CfnOutput(
            self,
            "TFPlanBucket",
            value=self.bucket_tfplan.bucket_name,
        )

        # tfplan
        
        self.bucket_codebuild_terraform_backend = aws_s3.Bucket(
            self,
            "CodeBuildTerraformBackend",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        
        self.bucket_tfplan_utils = aws_s3.Bucket(
            self,
            "TFPlanUtils",
            block_public_access=aws_s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        aws_s3_deployment.BucketDeployment(
            self,
            "ParseTFPlanOutputToCBInput",
            sources=[
                aws_s3_deployment.Source.asset(f"./supplementary_files/codebuild_utils/tfplan_utils")
            ],
            destination_bucket=self.bucket_tfplan_utils,
            retain_on_delete=False,
        )
        
        role_tfplan = aws_iam.Role(
            self,
            "TFPlanRole",
            assumed_by=aws_iam.ServicePrincipal("codebuild.amazonaws.com"),
        )

        role_tfplan.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:Get*",
                    "s3:List*",
                ],
                resources=[
                    self.bucket_tfplan.bucket_arn,
                    self.bucket_tfplan.arn_for_objects("*"),
                    self.bucket_codebuild_terraform_backend.bucket_arn,
                    self.bucket_codebuild_terraform_backend.arn_for_objects("*"),
                ],
            )
        )
        role_tfplan.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:PutObject",
                    "s3:Get*",
                    "s3:List*",
                ],
                resources=[
                    self.bucket_codebuild_terraform_backend.bucket_arn,
                    self.bucket_codebuild_terraform_backend.arn_for_objects("*"),
                ],
            )
        )
        role_tfplan.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "s3:GetObject",
                    "s3:Get*",
                    "s3:List*",
                ],
                resources=[
                    self.bucket_tfplan_utils.bucket_arn,
                    self.bucket_tfplan_utils.arn_for_objects("*"),
                ],
            )
        )
        role_tfplan.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "sqs:*", # required by IaC in example app
                ],
                resources=["*"]
            )
        )
        role_tfplan.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "codepipeline:GetPipelineState",
                ],
                resources=["*"],
            )
        )

        self.codebuild_to_sfn_artifact_file = "control-broker-consumer-inputs.json"
            
        build_project_tfplan = aws_codebuild.PipelineProject(
            self,
            "TFPlanProject",
            environment = aws_codebuild.BuildEnvironment(
                build_image = aws_codebuild.LinuxBuildImage.STANDARD_3_0
            ),
            role = role_tfplan,
            build_spec=aws_codebuild.BuildSpec.from_object(
                {
                    "version": "0.2",
                    "phases": {
                        "install": {
                            "on-failure": "ABORT",
                            "commands": [
                                "curl -s -qL -o terraform_install.zip https://releases.hashicorp.com/terraform/1.2.0/terraform_1.2.0_linux_386.zip",
                                "unzip terraform_install.zip -d /usr/bin/",
                                "chmod +x /usr/bin/terraform",
                                "terraform -version",
                            ],
                        },
                        "build": {
                            "on-failure": "ABORT",
                            "commands": [
                                "CODEPIPELINE_EXECUTION_ID=$(aws codepipeline get-pipeline-state --region us-east-1 --name ${CODEBUILD_INITIATOR#codepipeline/} --query 'stageStates[?actionStates[?latestExecution.externalExecutionId==`'${CODEBUILD_BUILD_ID}'`]].latestExecution.pipelineExecutionId' --output text)",
                                "echo $CODEPIPELINE_EXECUTION_ID",
                                "ls",
                                "echo ${CodeBuildTerraformBackendBucket}",
                                "terraform init -backend-config=\"bucket=${CodeBuildTerraformBackendBucket}\" -backend-config=\"region=us-east-1\"",
                                "terraform plan --out tfplan.binary && terraform show -json tfplan.binary > tfplan.json",
                                "ls",
                                f"aws s3 sync s3://{self.bucket_tfplan_utils.bucket_name} .",
                                "pip install -r requirements.txt",
                                f"python3 parse_tfplan_to_cb_input.py {self.codebuild_to_sfn_artifact_file} $CODEPIPELINE_EXECUTION_ID",
                            ],
                        },
                    },
                    "artifacts": {
                        "files": ["**/*"],
                        "discard-paths": "no",
                        "enable-symlinks": "yes",
                    },
                }
            ),
            environment_variables={
                "TFPlanBucket": aws_codebuild.BuildEnvironmentVariable(value=self.bucket_tfplan.bucket_name),
                "PipelineOwnershipMetadata": aws_codebuild.BuildEnvironmentVariable(value=json.dumps(self.pipeline_ownership_metadata)),
                "CodeBuildTerraformBackendBucket": aws_codebuild.BuildEnvironmentVariable(value=self.bucket_codebuild_terraform_backend.bucket_name),
            }
            
        )

        self.artifact_built = aws_codepipeline.Artifact()

        self.action_build = aws_codepipeline_actions.CodeBuildAction(
            action_name="CodeBuildCdkSynth",
            project=build_project_tfplan,
            input=self.artifact_source,
            outputs=[self.artifact_built],
        )
    
    def evaluate_wrapper_sfn_lambdas(self):
    
        # sign apigw request
        
        self.lambda_sign_apigw_request = aws_lambda_python_alpha.PythonFunction(
            self,
            "SignApigwRequestVAlpha",
            entry="./supplementary_files/lambdas/sign_apigw_request",
            runtime= aws_lambda.Runtime.PYTHON_3_9,
            index="lambda_function.py",
            handler="lambda_handler",
            timeout=Duration.seconds(60),
            memory_size=1024,
            environment = {
                "ApigwInvokeUrl" : self.control_broker_apigw_url,
                "PipelineOwnershipMetadata": json.dumps(self.pipeline_ownership_metadata),
            },
            layers=[
                self.layers['requests'],
                self.layers['aws_requests_auth'],
            ]
        )

        if self.source_iac == "CDK":
            
            self.lambda_sign_apigw_request.role.add_to_policy(
                aws_iam.PolicyStatement(
                    actions=[
                        "s3:GetObject",
                        "s3:GetBucket",
                        "s3:List*",
                    ],
                    resources=[
                        self.bucket_synthed_templates.bucket_arn,
                        self.bucket_synthed_templates.arn_for_objects("*"),
                    ],
                )
            )
        if self.source_iac == "Terraform":

            self.lambda_sign_apigw_request.role.add_to_policy(
                aws_iam.PolicyStatement(
                    actions=[
                        "s3:GetObject",
                        "s3:GetBucket",
                        "s3:List*",
                    ],
                    resources=[
                        self.bucket_tfplan.bucket_arn,
                        self.bucket_tfplan.arn_for_objects("*"),
                    ],
                )
            )
        
        #requests get
        
        self.lambda_requests_get = aws_lambda.Function(
            self,
            "RequestsGet",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            timeout=Duration.seconds(60),
            memory_size=1024,
            code=aws_lambda.Code.from_asset(
                "./supplementary_files/lambdas/requests_get"
            ),
            layers=[
                self.layers['requests'],
            ]
        )
        
        # determine if all CodeBuild inputs compliant
       
        self.lambda_parse_results_detemine_compliance = aws_lambda.Function(
            self,
            "ParseResultsDetermineCompliance",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            timeout=Duration.seconds(60),
            memory_size=1024,
            code=aws_lambda.Code.from_asset(
                "./supplementary_files/lambdas/parse_results_determine_compliance"
            ),
        )
        
    def evaluate_wrapper_sfn(self):

        role_eval_engine_wrapper = aws_iam.Role(
            self,
            "CB-Consumer-IaCPipeline-Sfn",
            assumed_by=aws_iam.ServicePrincipal("states.amazonaws.com"),
        )
        
        role_eval_engine_wrapper.add_to_policy(
            aws_iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[
                    self.lambda_sign_apigw_request.function_arn,
                    self.lambda_requests_get.function_arn,
                    self.lambda_parse_results_detemine_compliance.function_arn,
                ],
            )
        )

        states_json ={
            "StartAt": "ForEachCodeBuildInput",
            "States": {
                "ForEachCodeBuildInput": {
                    "Type": "Map",
                    "Next": "ParseResultsDetermineCompliance",
                    "ResultPath": "$.ForEachCodeBuildInput",
                    "ItemsPath": "$.CodeBuildToSfnArtifact.CodeBuildInputs",
                    "Parameters": {
                        "CodeBuildInput.$":"$$.Map.Item.Value",
                        "Context.$":"$.CodeBuildToSfnArtifact.Context"
                    },
                    "Iterator": {
                        "StartAt": "SignApigwRequest",
                        "States": {
                            "SignApigwRequest": {
                                "Type": "Task",
                                "Next": "GetIsCompliant",
                                "ResultPath": "$.SignApigwRequest",
                                "Resource": "arn:aws:states:::lambda:invoke",
                                "Parameters": {
                                    "FunctionName": self.lambda_sign_apigw_request.function_name,
                                    "Payload": {
                                        "Input": {
                                            "Bucket.$":"$.CodeBuildInput.Bucket",
                                            "Key.$":"$.CodeBuildInput.Key",
                                        },
                                        "Context.$":"$.Context" 
                                    }
                                },
                                "ResultSelector": {
                                    "Payload.$": "$.Payload"
                                },
                                "Catch": [
                                    {
                                        "ErrorEquals":[
                                            "APIGWNot200Exception"
                                        ],
                                        "Next": "APIGWNot200"
                                    }
                                ]
                            },
                            "APIGWNot200": {
                                "Type":"Fail"
                            },
                            "GetIsCompliant": {
                                "Type": "Task",
                                "Next": "ChoiceIsCompliant",
                                "ResultPath": "$.GetIsCompliant",
                                "Resource": "arn:aws:states:::lambda:invoke",
                                "Parameters": {
                                    "FunctionName": self.lambda_requests_get.function_name,
                                    "Payload":{
                                        "Url.$":"$.SignApigwRequest.Payload.Response.ControlBrokerEvaluation.OutputHandlers.OPA.PresignedUrl",
                                    }
                                },
                                "ResultSelector": {
                                    "Payload.$": "$.Payload"
                                },
                                "Retry": [
                                    {
                                        "ErrorEquals": [
                                            "StatusCodeNot200Exception"
                                        ],
                                        "IntervalSeconds": 1,
                                        "MaxAttempts": 8,
                                        "BackoffRate": 2.0
                                    }
                                ],
                                "Catch": [
                                    {
                                        "ErrorEquals":[
                                            "States.ALL"
                                        ],
                                        "Next": "ResultsReportDoesNotYetExist"
                                    }
                                ]
                            },
                            "ResultsReportDoesNotYetExist": {
                                "Type":"Fail"
                            },
                            "ChoiceIsCompliant": {
                                "Type":"Choice",
                                "Default":"IsCompliantFalse",
                                "Choices":[
                                    {
                                        "Variable":"$.GetIsCompliant.Payload.EvalEngineLambdalith.Evaluation.IsCompliant",
                                        "BooleanEquals":True,
                                        "Next":"IsCompliantTrue"
                                    },
                                ]
                            },
                            "IsCompliantTrue":{
                                "Type":"Pass",
                                "End":True
                            },
                            "IsCompliantFalse":{
                                "Type":"Pass",
                                "End":True
                            }
                        }
                    }
                },
                "ParseResultsDetermineCompliance": {
                    "Type": "Task",
                    "Next": "ChoiceAllCodeBuildInputsCompliant",
                    "ResultPath": "$.ParseResultsDetermineCompliance",
                    "Resource": "arn:aws:states:::lambda:invoke",
                    "Parameters": {
                        "FunctionName": self.lambda_parse_results_detemine_compliance.function_name,
                        "Payload.$": "$"
                    },
                    "ResultSelector": {
                        "Payload.$": "$.Payload"
                    },
                },
                "ChoiceAllCodeBuildInputsCompliant": {
                    "Type":"Choice",
                    "Default":"AllCodeBuildInputsCompliantFalse",
                    "Choices":[
                        {
                            "Variable":"$.ParseResultsDetermineCompliance.Payload.AllCodeBuildInputsCompliant",
                            "BooleanEquals":True,
                            "Next":"AllCodeBuildInputsCompliantTrue"
                        },
                    ]
                },
                "AllCodeBuildInputsCompliantTrue":{
                    "Type":"Succeed",
                },
                "AllCodeBuildInputsCompliantFalse":{
                    "Type":"Fail",
                }
            }
        }
        
        placeholder = aws_stepfunctions.Succeed(self, "Placeholder")

        chain = aws_stepfunctions.Chain.start(placeholder)
        
        sfn_l2_control_broker_client = aws_stepfunctions.StateMachine(self, "CB-Consumer-IaCPipeline",
            definition=chain,
            role = role_eval_engine_wrapper
        )
        
        sfn_l1_control_broker_client = sfn_l2_control_broker_client.node.default_child
        
        sfn_l1_control_broker_client.add_property_override(
            "DefinitionString",
            json.dumps(states_json)
        )
        
        self.action_eval_engine = aws_codepipeline_actions.StepFunctionInvokeAction(
            action_name="Invoke",
            state_machine=sfn_l2_control_broker_client,
            state_machine_input=aws_codepipeline_actions.StateMachineInput.file_path(
                aws_codepipeline.ArtifactPath(
                    self.artifact_built,
                    self.codebuild_to_sfn_artifact_file
                )
            )
        )
        
    def pipeline(self):
        synth_eval_pipeline = aws_codepipeline.Pipeline(
            self,
            "ControlBrokerEvalEngine",
            artifact_bucket=aws_s3.Bucket(
                self,
                "RootPipelineArtifactBucket",
                removal_policy=RemovalPolicy.DESTROY,
                auto_delete_objects=True,
            ),
            stages=[
                aws_codepipeline.StageProps(
                    stage_name="Source", actions=[self.action_source]
                ),
                aws_codepipeline.StageProps(
                    stage_name="Build", actions=[self.action_build]
                ),
                aws_codepipeline.StageProps(
                    stage_name="EvalEngine", actions=[self.action_eval_engine]
                ),
                # aws_codepipeline.StageProps(
                #     stage_name="CdkDeploy", actions=[action_build_cdk_deploy]
                # ),
            ],
        )
# 