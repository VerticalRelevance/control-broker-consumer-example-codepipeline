def lambda_handler(event,context):
    
    print(event)
    
    all_codebuild_inputs_compliant = True # FIXME
    
    return {
        "AllCodeBuildInputsCompliant": all_codebuild_inputs_compliant
    }