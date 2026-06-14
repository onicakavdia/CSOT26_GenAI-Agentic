Step1 : Got introduced to the OpenAI and different models ,learned about what the API keys do, how they work, how to store them and how to keep them safe so that it's mot published by storing it in the .gitignore file before commiting it. Learnt how my code is being connected to the openrouter and from i am able to chat with a model.


Step2: Task was to make a multi-turn conversation chatbot for which I had to store all the chat that is being done and the answers given so that my chatbot can have the information about the chat because LLM have no memory so I decided to create a class in which I can collect all the information under different objects and so that I am not hardcoding and letting the user decide which model they have to work with. For that I studied that the self is best in which I can use my information of one def function to other.

So I used class and in that various def function so that all the conversation can be stored and added one by one as thay are done .

As asked I added exit option as soon as the conversation is completed.
I also added the chat compaction area which when the length of the conversation goes higher than 11 it can initiate and then summarize the whole conversation.


Step3 : To run all this in a loop and so that the conversation goes on without any break I created another function in which a loop goes on as the conversattion does.

also added a reset button so that user can reset everything whenever needed.
