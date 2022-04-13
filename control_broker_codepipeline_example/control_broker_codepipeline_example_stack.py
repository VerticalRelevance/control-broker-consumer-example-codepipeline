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
)
from constructs import Construct


class ControlBrokerCodepipelineExampleStack(Stack):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        control_broker_template_reader_arns: List[str],
        control_broker_sfn_invoke_arn: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        # Give read permission to the control broker on the templates we store
        # and pass to the control broker
        for control_broker_principal_arn in control_broker_template_reader_arns:
            self.bucket_synthed_templates.grant_read(
                aws_iam.ArnPrincipal(control_broker_principal_arn)
            )

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

        artifact_source = aws_codepipeline.Artifact()

        action_source = aws_codepipeline_actions.CodeCommitSourceAction(
            action_name="CodeCommit",
            repository=self.repo_app_team_cdk,
            branch="main",
            output=artifact_source,
        )
        
        # synth

        build_project_cdk_synth = aws_codebuild.PipelineProject(
            self,
            "CdkSynth",
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
                                "ls",
                                "cdk synth",
                                "ls",
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
        )

        artifact_synthed = aws_codepipeline.Artifact()

        action_build_cdk_synth = aws_codepipeline_actions.CodeBuildAction(
            action_name="CodeBuildCdkSynth",
            project=build_project_cdk_synth,
            input=artifact_source,
            outputs=[artifact_synthed],
        )
        
        # eval
        
        log_group_eval_engine_wrapper = aws_logs.LogGroup(
            self,
            "EvalEngineWrapperSfnLogs",
            log_group_name="/aws/vendedlogs/states/EvalEngineWrapperSfnLogs",
            removal_policy=RemovalPolicy.DESTROY,
        )

        role_eval_engine_wrapper = aws_iam.Role(
            self,
            "EvalEngineWrapperSfn",
            assumed_by=aws_iam.ServicePrincipal("states.amazonaws.com"),
        )

        role_eval_engine_wrapper.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    # "logs:*",
                    "logs:CreateLogDelivery",
                    "logs:GetLogDelivery",
                    "logs:UpdateLogDelivery",
                    "logs:DeleteLogDelivery",
                    "logs:ListLogDeliveries",
                    "logs:PutResourcePolicy",
                    "logs:DescribeResourcePolicies",
                    "logs:DescribeLogGroups",
                ],
                resources=[
                    "*",
                    log_group_eval_engine_wrapper.log_group_arn,
                    f"{log_group_eval_engine_wrapper.log_group_arn}*",
                ],
            )
        )
        role_eval_engine_wrapper.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "states:DescribeExecution",
                    "states:StopExecution"
                ],
                resources=[
                    "*"
                ],
            )
        )
        role_eval_engine_wrapper.add_to_policy(
            aws_iam.PolicyStatement(
                actions=[
                    "events:PutTargets",
                    "events:PutRule",
                    "events:DescribeRule"
                ],
                resources=[
                    f"arn:aws:events:{os.getenv('CDK_DEFAULT_REGION')}:{os.getenv('CDK_DEFAULT_ACCOUNT')}:rule/StepFunctionsGetEventsForStepFunctionsExecutionRule",
                    "*",
                ],
            )
        )

        # In real life, you'd probably have a stack set in each consumer
        # account that would register the account with the control broker
        # and create a role inside the account with permissions to invoke
        # the control broker.
        # role_eval_engine_wrapper.add_to_policy(
        #     aws_iam.PolicyStatement(
        #         actions=[
        #             "states:StartSyncExecution",
        #         ],
        #         resources=[
        #             control_broker_sfn_invoke_arn,
        #             f"{control_broker_sfn_invoke_arn}*",
        #         ],
        #     )
        # )

        # self.sfn_eval_engine_wrapper = aws_stepfunctions.CfnStateMachine(
        #     self,
        #     "EvalEngineWrapper",
        #     state_machine_type="STANDARD",
        #     role_arn=role_eval_engine_wrapper.role_arn,
        #     logging_configuration=aws_stepfunctions.CfnStateMachine.LoggingConfigurationProperty(
        #         destinations=[
        #             aws_stepfunctions.CfnStateMachine.LogDestinationProperty(
        #                 cloud_watch_logs_log_group=aws_stepfunctions.CfnStateMachine.CloudWatchLogsLogGroupProperty(
        #                     log_group_arn=log_group_eval_engine_wrapper.log_group_arn
        #                 )
        #             )
        #         ],
        #         include_execution_data=False,
        #         level="ERROR",
        #     ),
        #     definition_string=json.dumps(
        #         {
        #             "StartAt": "ParseInput",
        #             "States": {
        #                 "ParseInput": {
        #                     "Type": "Pass",
        #                     "End": True,
        #                 }
        #             }
        #         }
        #     )
        # )

        self.sfn_eval_engine_wrapper.node.add_dependency(role_eval_engine_wrapper)

        state_json = {
            "StartAt": "ParseInput",
            "States": {
                "ParseInput": {
                    "Type": "Pass",
                    "Next":"GetLatestCodePipelineExecutionId"
                },
                "GetLatestCodePipelineExecutionId": {
                    "Type": "Pass",
                    "End":True
                },
            }
        }
        
        ParseInput = aws_stepfunctions.CustomState(self, "ParseInput",
            state_json=state_json['States']['ParseInput']
        )
        GetLatestCodePipelineExecutionId = aws_stepfunctions.CustomState(self, "GetLatestCodePipelineExecutionId",
            state_json=state_json['States']['GetLatestCodePipelineExecutionId']
        )
        
        chain = aws_stepfunctions.Chain.start(ParseInput).next(GetLatestCodePipelineExecutionId)
        
        simple_state_machine = aws_stepfunctions.StateMachine(self, "EvalEngineWrapper",
            definition=chain,
            role = role_eval_engine_wrapper
        )
        
        action_eval_engine = aws_codepipeline_actions.StepFunctionInvokeAction(
            action_name="Invoke",
            # state_machine=self.sfn_eval_engine_wrapper,
            state_machine=simple_state_machine,
            state_machine_input=aws_codepipeline_actions.StateMachineInput.literal({"IsHelloWorldExample": True})
        )
        

        
        # lambda_eval_engine_wrapper = aws_lambda.Function(
        #     self,
        #     "EvalEngineWrapper",
        #     runtime=aws_lambda.Runtime.PYTHON_3_9,
        #     handler="lambda_function.lambda_handler",
        #     timeout=Duration.seconds(60),
        #     memory_size=1024,
        #     code=aws_lambda.Code.from_asset(
        #         "./supplementary_files/lambdas/eval-engine-wrapper"
        #     ),
        # )

        # lambda_eval_engine_wrapper.role.add_to_policy(
        #     aws_iam.PolicyStatement(
        #         actions=[
        #             "s3:PutObject",
        #         ],
        #         resources=[f"{self.bucket_synthed_templates.bucket_arn}/*"],
        #     )
        # )

        # # In real life, you'd probably have a stack set in each consumer
        # # account that would register the account with the control broker
        # # and create a role inside the account with permissions to invoke
        # # the control broker.
        # lambda_eval_engine_wrapper.role.add_to_policy(
        #     aws_iam.PolicyStatement(
        #         actions=[
        #             "states:StartSyncExecution",
        #         ],
        #         resources=[
        #             control_broker_sfn_invoke_arn,
        #             f"{control_broker_sfn_invoke_arn}*",
        #         ],
        #     )
        # )

        # action_eval_engine = aws_codepipeline_actions.LambdaInvokeAction(
        #     action_name="EvalEngine",
        #     inputs=[artifact_synthed],
        #     lambda_=lambda_eval_engine_wrapper,
        #     user_parameters={
        #         "SynthedTemplatesBucket": self.bucket_synthed_templates.bucket_name,
        #         "EvalEngineSfnArn": control_broker_sfn_invoke_arn,
        #     },
        # )

        # deploy

        # role_cdk_deploy = aws_iam.Role(
        #     self,
        #     "RoleCdkDeploy",
        #     assumed_by=aws_iam.ServicePrincipal("codebuild.amazonaws.com"),
        # )
        # role_cdk_deploy.add_to_policy(
        #     aws_iam.PolicyStatement(
        #         not_actions=[
        #             "cloudformation:Delete*",
        #         ],
        #         resources=[
        #             "*",
        #         ],
        #     )
        # )

        # build_project_cdk_deploy = aws_codebuild.PipelineProject(
        #     self,
        #     "CdkDeploy",
        #     role=role_cdk_deploy,
        #     build_spec=aws_codebuild.BuildSpec.from_object(
        #         {
        #             "version": "0.2",
        #             "phases": {
        #                 "install": {
        #                     "on-failure": "ABORT",
        #                     "commands": [
        #                         # TODO upgrade node, v10 deprecated
        #                         "npm install -g typescript",
        #                         "npm install -g ts-node",
        #                         "npm install -g aws-cdk",
        #                         "npm install",
        #                         "cdk --version",
        #                     ],
        #                 },
        #                 "build": {
        #                     "on-failure": "ABORT",
        #                     "commands": [
        #                         "ls",
        #                         "cdk deploy --all --require-approval never",
        #                     ],
        #                 },
        #             },
        #         }
        #     ),
        # )

        # action_build_cdk_deploy = aws_codepipeline_actions.CodeBuildAction(
        #     action_name="CodeBuildCdkDeploy",
        #     project=build_project_cdk_deploy,
        #     input=artifact_synthed,
        # )

        aws_codepipeline.Pipeline(
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
                    stage_name="Source", actions=[action_source]
                ),
                aws_codepipeline.StageProps(
                    stage_name="CdkSynth", actions=[action_build_cdk_synth]
                ),
                aws_codepipeline.StageProps(
                    stage_name="EvalEngine", actions=[action_eval_engine]
                ),
                # aws_codepipeline.StageProps(
                #     stage_name="CdkDeploy", actions=[action_build_cdk_deploy]
                # ),
            ],
        )
