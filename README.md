# Introduction
This is a custom integration for nymea/maveo.
It currently supports the following devices:
- maveo stick: open/close the garage and get its state
- maveo sensor: humidity and temperature sensor
- aqara weather sensor: humidity, temperature, pressure


# Disclaimer
I have never written a custom component for home assistant and I have had no contact to python before. The code quality is accordingly, sorry for that.
It is more or less a proof of concept which needs to be improved massively.

# Resources
The code for the home assistant integration is based on https://github.com/home-assistant/example-custom-config/tree/master/custom_components/detailed_hello_world_push.

The code to interact with nymea is taken from https://github.com/nymea/nymea-cli

# TODOs
- switch to push instead of poll
- use zeroconf (https://developers.home-assistant.io/docs/network_discovery#mdnszeroconf)
- cert pinning
- extract api specific code to a third party lib, see https://developers.home-assistant.io/docs/creating_component_code_review/#4-communication-with-devicesservices
- add tests