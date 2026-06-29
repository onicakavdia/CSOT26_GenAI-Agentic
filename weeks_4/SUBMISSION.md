# SUBMISSION.md

## What I built

So basically I built a coding agent called Code Scout. You give it a task in plain English like "this test is failing, go fix it" and it figures out the rest on its own - it looks through the project files, finds the right code, makes a plan, fixes it, and then actually re-runs the tests to check it really worked instead of just saying "yep fixed it" and hoping.

The main thing I was told to focus on was the safety part. The agent can do real stuff - run commands, edit files - but anything that could actually break something has to stop and ask me first with a yes/no question. So like if it wants to run `ls` or `grep`, it just does it, no asking. But if it wants to edit a file or run something like `git push` or `pip install`, it stops and shows me exactly what it's about to do and waits for me to type y or n. I thought this was a pretty important part of the assignment so I tried to make sure literally every risky thing goes through that same check, not just some of them.

I'm not super experienced with this stuff so I kept the code pretty plain - basically everything is just normal functions, not a lot of fancy classes or anything, so I could actually keep track of what's going on. It's all in one file (agent.py) which I know isn't the "proper" way to organize a bigger project but it made it way easier for me to not lose track of how the pieces connect to each other.

One thing - I didn't have a real GitHub repo to point this at, so the script just makes its own tiny fake project the first time you run it. It creates a small Python file with a bug on purpose (a password checker that wrongly rejects 8-character passwords) plus a test that fails because of that bug. That way you can literally just run the script and it has something real to go fix immediately, no extra setup needed.

## Repo used

Like I said above, it's the little demo project the script makes for itself (`target_repo/`). It's not a big real codebase, it's just enough to actually test that the agent can find a bug, fix it, and verify the fix worked. I think the tools I wrote (list_files, read_file, run_command etc) don't really care what's inside the repo, so if I pointed it at an actual real project on github it should work the same way, I just didn't get around to trying that.


## What I'd do better with more time

Honestly if I had more time I'd test this on an actual real repo from github instead of my little made-up one, just to see if it holds up on something bigger and messier. Also my list_definitions function is pretty basic - it just looks for lines starting with "def" or "class", it's not a real parser, so on a more complicated file it could probably miss stuff or get confused. I kept it simple on purpose since I'm still learning but I know it's not as solid as it could be.
