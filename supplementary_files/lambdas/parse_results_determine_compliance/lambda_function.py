def lambda_handler(event,context):
    
    print(event)
    
    all_codebuild_inputs = [i['GetIsCompliant']['Payload']['EvalEngineLambdalith']['Evaluation']['IsCompliant'] for i in event['ForEachCodeBuildInput']]

    print(all_codebuild_inputs)
    
    all_codebuild_inputs_compliant = all(all_codebuild_inputs)
    
    print(f'all_codebuild_inputs_compliant:\n{all_codebuild_inputs_compliant}')
    
    return {
        "AllCodeBuildInputsCompliant": all_codebuild_inputs_compliant
    }