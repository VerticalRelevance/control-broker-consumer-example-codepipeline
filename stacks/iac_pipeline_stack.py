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
    aws_lambda_python_alpha, #experimental
)
from constructs import Construct


class ControlBrokerCodepipelineExampleStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        control_broker_input_reader_arns: List[str],
        control_broker_apigw_url:str,
        pipeline_ownership_metadata:dict,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)
        
        self.pipeline_ownership_metadata = pipeline_ownership_metadata
        self.control_broker_input_reader_arns = control_broker_input_reader_arns
        self.control_broker_apigw_url = control_broker_apigw_url
        
        self.source()
        self.synth()
        # self.evaluate_wrapper_sfn_lambdas()
        self.evaluate_wrapper_sfn()
        self.pipeline()
    
    def source(self):
    
        # source

        self.repo_app_team_cdk = aws_codecommit.Repository(
            self,
            "ApplicationTeamExampleAppRepository",
            repository_name="ControlBrokerEvalEngine-ApplicationTeam-ExampleApp",
            code=aws_codecommit.Code.from_directory(
                "./supplementary_files/application_team_example_app", "main"
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

        # Give read permission to the control broker on the Consumer Inputs we store
        # and pass to the control broker
        for control_broker_principal_arn in self.control_broker_input_reader_arns:
            self.bucket_synthed_templates.grant_read(
                aws_iam.ArnPrincipal(control_broker_principal_arn)
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
                aws_s3_deployment.Source.asset(f"./supplementary_files/synth_utils")
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
                    self.bucket_synthed_templates.bucket_name,
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
                    self.bucket_synth_utils.bucket_name,
                    self.bucket_synth_utils.arn_for_objects("*"),
                ],
            )
        )

        # synthed templates namespaced to some pipeline owner / app team ID, TODO: determine pipeline metadata strategy
        
        # synthed_templates_s3_uri_root = f"s3://{self.bucket_synthed_templates.bucket_name}/{self.pipeline_ownership_metadata['PipelineId']}/RecentTemplates"
        
        # synthed templates not namespaced by pipeline owner / app team ID - potential name collisions?
        
        synthed_templates_s3_uri_root = f"s3://{self.bucket_synthed_templates.bucket_name}/"

        def s3_uri_to_bucket(*,Uri):
            path_parts=Uri.replace("s3://","").split("/")
            bucket=path_parts.pop(0)
            return bucket
            
        def s3_uri_to_key(*,Uri):
            path_parts=Uri.replace("s3://","").split("/")
            bucket=path_parts.pop(0)
            key="/".join(path_parts)
            return key
        
        self.codebuild_to_sfn_artifact_file = "control-broker-consumer-inputs.json"
            
        build_project_cdk_synth = aws_codebuild.PipelineProject(
            self,
            "CdkSynth",
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

        self.artifact_synthed = aws_codepipeline.Artifact()

        self.action_build_cdk_synth = aws_codepipeline_actions.CodeBuildAction(
            action_name="CodeBuildCdkSynth",
            project=build_project_cdk_synth,
            input=self.artifact_source,
            outputs=[self.artifact_synthed],
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
                "ApigwInvokeUrl" : self.control_broker_apigw_url
            },
            layers=[
                aws_lambda_python_alpha.PythonLayerVersion(
                    self,
                    "aws_requests_auth",
                    entry="./supplementary_files/lambda_layers/aws_requests_auth",
                    compatible_runtimes=[
                        aws_lambda.Runtime.PYTHON_3_9
                    ]
                ),
                aws_lambda_python_alpha.PythonLayerVersion(self,
                    "requests",
                    entry="./supplementary_files/lambda_layers/requests",
                    compatible_runtimes=[
                        aws_lambda.Runtime.PYTHON_3_9
                    ]
                ),
            ]
        )
        
        # object exists
        
        self.lambda_object_exists = aws_lambda.Function(
            self,
            "ObjectExists",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            timeout=Duration.seconds(60),
            memory_size=1024,
            code=aws_lambda.Code.from_asset(
                "./supplementary_files/lambdas/s3_head_object"
            ),
        )
        
        # s3 select
        
        self.lambda_s3_select = aws_lambda.Function(
            self,
            "S3Select",
            runtime=aws_lambda.Runtime.PYTHON_3_9,
            handler="lambda_function.lambda_handler",
            timeout=Duration.seconds(60),
            memory_size=1024,
            code=aws_lambda.Code.from_asset("./supplementary_files/lambdas/s3_select"),
        )
    
    def evaluate_wrapper_sfn(self):

        role_eval_engine_wrapper = aws_iam.Role(
            self,
            "CB-Consumer-IaCPipeline-Sfn",
            assumed_by=aws_iam.ServicePrincipal("states.amazonaws.com"),
        )

        # role_eval_engine_wrapper.add_to_policy(
        #     aws_iam.PolicyStatement(
        #         actions=["lambda:InvokeFunction"],
        #         resources=[
        #             self.lambda_sign_apigw_request.function_arn,
        #             self.lambda_object_exists.function_arn,
        #             self.lambda_s3_select.function_arn
        #         ],
        #     )
        # )

        states_json ={
            "StartAt": "SignApigwRequest",
            "States": {
                "SignApigwRequest": {
                    "Type": "Succeed",
                }
            }
        }
        #             "Type": "Task",
        #             "Next": "CheckResultsReportExists",
        #             "ResultPath": "$.SignApigwRequest",
        #             "Resource": "arn:aws:states:::lambda:invoke",
        #             "Parameters": {
        #                 "FunctionName": self.lambda_sign_apigw_request.function_name,
        #                 "Payload.$": "$"
        #             },
        #             "ResultSelector": {
        #                 "Payload.$": "$.Payload"
        #             },
        #             "Catch": [
        #                 {
        #                     "ErrorEquals":[
        #                         "APIGWNot200Exception"
        #                     ],
        #                     "Next": "APIGWNot200"
        #                 }
        #             ]
        #         },
        #         "APIGWNot200": {
        #             "Type":"Fail"
        #         },
        #         "CheckResultsReportExists": {
        #             "Type": "Task",
        #             "Next": "GetResultsReportIsCompliantBoolean",
        #             "ResultPath": "$.CheckResultsReportExists",
        #             "Resource": "arn:aws:states:::lambda:invoke",
        #             "Parameters": {
        #                 "FunctionName": self.lambda_object_exists.function_name,
        #                 "Payload": {
        #                     "S3Uri.$":"$.SignApigwRequest.Payload.ControlBrokerRequestStatus.ResultsReportS3Uri"
        #                 }
        #             },
        #             "ResultSelector": {
        #                 "Payload.$": "$.Payload"
        #             },
        #             "Retry": [
        #                 {
        #                     "ErrorEquals": [
        #                         "ObjectDoesNotExistException"
        #                     ],
        #                     "IntervalSeconds": 1,
        #                     "MaxAttempts": 6,
        #                     "BackoffRate": 2.0
        #                 }
        #             ],
        #             "Catch": [
        #                 {
        #                     "ErrorEquals":[
        #                         "States.ALL"
        #                     ],
        #                     "Next": "ResultsReportDoesNotYetExist"
        #                 }
        #             ]
        #         },
        #         "ResultsReportDoesNotYetExist": {
        #             "Type":"Fail"
        #         },
        #         "GetResultsReportIsCompliantBoolean": {
        #             "Type": "Task",
        #             "Next": "ChoiceIsComplaint",
        #             "ResultPath": "$.GetResultsReportIsCompliantBoolean",
        #             "Resource": "arn:aws:states:::lambda:invoke",
        #             "Parameters": {
        #                 "FunctionName": self.lambda_s3_select.function_name,
        #                 "Payload": {
        #                     "S3Uri.$":"$.SignApigwRequest.Payload.ControlBrokerRequestStatus.ResultsReportS3Uri",
        #                     "Expression": "SELECT * from S3Object s",
        #                 },
        #             },
        #             "ResultSelector": {"S3SelectResult.$": "$.Payload.Selected"},
        #         },
        #         "ChoiceIsComplaint": {
        #             "Type":"Choice",
        #             "Default":"CompliantFalse",
        #             "Choices":[
        #                 {
        #                     "Variable":"$.GetResultsReportIsCompliantBoolean.S3SelectResult.ControlBrokerResultsReport.Evaluation.IsCompliant",
        #                     "BooleanEquals":True,
        #                     "Next":"CompliantTrue"
        #                 }
        #             ]
        #         },
        #         "CompliantTrue": {
        #             "Type":"Succeed"
        #         },
        #         "CompliantFalse": {
        #             "Type":"Fail"
        #         }
        #     }
        # }
        
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
                    self.artifact_synthed,
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
                    stage_name="CdkSynth", actions=[self.action_build_cdk_synth]
                ),
                aws_codepipeline.StageProps(
                    stage_name="EvalEngine", actions=[self.action_eval_engine]
                ),
                # aws_codepipeline.StageProps(
                #     stage_name="CdkDeploy", actions=[action_build_cdk_deploy]
                # ),
            ],
        )
