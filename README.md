# URL-Shortener-App

A small backend application for creating a short url for a given url.

###This repo consists of 4 files.

1. Dockerfile - This file is used to create a docker image

2. requirements.txt - It contains all the module that are needed to run the code

3. url_shortener.py - It contains the logic to create a short url.

##Steps to run -

1. Clone the repository

2. cd /URL-Shortener-App

3. Create a virtual environment and activate the virtual environment -
    python3 -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
4. Run python url_shortener.py command
   This will run the flask server on the port 127.0.0.1:5000

##Test the application:

1. Make a curl request -
   curl -X POST -H "Content-Type: application/json" -d '{
      "longUrl": "https://www.python.org/",
      "customAlias": "pythonlang" \\You can omit this parameter as well. This is used for customAlias that should be included
    }' http://localhost:5000/api/shorten
2. It will return something like this in response -
   {
      "longUrl": "https://www.python.org/",
      "shortCode": "pythonlang",
      "shortUrl": "http://localhost:5000/pythonlang"
   }
3. You can copy the shortUrl you get in the previous step and just paste it in the browser. It should take you to the actual url.

   
