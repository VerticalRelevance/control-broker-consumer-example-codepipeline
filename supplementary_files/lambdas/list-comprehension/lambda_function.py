def lambda_handler(event,context):
    print(event)
    
    return [i[event['Key']] for i in event['List']]