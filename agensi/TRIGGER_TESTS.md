# Trigger tests: Desk Mesh Doctor

Agensi's pre-publish rule: the skill should trigger on 5 of 5 relevant prompts and 0 of 5 unrelated ones. If it
triggers on fewer than 4 relevant prompts, the description is too narrow. If it triggers on more than 1 unrelated
prompt, it is too broad.

Status: **not yet run in an agent.** Run each prompt in a fresh session with the skill installed, tick the box when
the result is right, and record the agent and date. Run again after a model update.

## Should trigger

- [ ] My mouse won't move over to my other computer even though they're on the same wifi
- [ ] Clipboard sharing between my Mac and my PC stopped working yesterday
- [ ] My phone can't find my laptop on my home network, what's blocking it?
- [ ] Why can't my laptop connect to my desktop? Pinging works but the sharing app times out
- [ ] File transfers to my tablet keep failing halfway, is it my router or my firewall?

## Should not trigger

- [ ] Which is better for sharing a keyboard between two computers, a software tool or a hardware switch?
- [ ] My internet has been down since this morning, how do I call my provider?
- [ ] Set up port forwarding on my router so I can reach my home server from outside
- [ ] Why is my remote desktop picture blurry and low resolution?
- [ ] Write a Python script that sends a file over a socket

## Record

| Agent | Date | Relevant (of 5) | Unrelated that triggered (of 5) |
|---|---|---|---|
