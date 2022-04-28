import sys

first_arg = sys.argv[1]
print(f'first_arg:\n{first_arg}\n{type(first_arg)}')

synth_to_sfn_input_file = first_arg

control_broker_consumer_inputs = {
    "ControlBrokerConsumerInputs":{
        "Bucket": "FIXME",
        "ConsumerMetadata": "FIXME",
        "InputKeys":[
            "A",
            "B"
        ]
    }
}

with open(synth_to_sfn_input_file,'w') as f:
    json.dump(control_broker_consumer_inputs,f,indent=2)