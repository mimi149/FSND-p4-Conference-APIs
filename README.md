## p4_Conference_APIs
This project, the fourth in [Udacity’s Full Stack Web Developer Nanodegree](https://www.udacity.com/course/full-stack-web-developer-nanodegree--nd004), focuses on using Google Cloud Platform to develop a scalable web app, and it's built with Google App Engine (Python), Google NDB Datastore, and Google Cloud Endpoints.

You can see more details about the project design and implementation in readme_full.pdf.

You can find out all APIs at [https://apis-explorer.appspot.com/apis-explorer/?base=https://p4conference.appspot.com/_ah/api#p/conference/v1/](https://apis-explorer.appspot.com/apis-explorer/?base=https://p4conference.appspot.com/_ah/api#p/conference/v1/)

You can check out the demo web page at [https://p4conference.appspot.com](https://p4conference.appspot.com)
Currently, the demo page does not support all functionality.

This cloud-based API server lets you organize conferences and sessions, and currently has following functionality:

1. User authentication
2. Create, read, update conferences
3. Register/ unregister for conferences
4. Create and read speakers for sessions
5. Create and read sessions for conferences (only the organizer of the conference can create its sessions.)
6. Add/ remove sessions to user's wishlist
7. Query for sessions and conferences.
 
### Products
[App Engine](https://cloud.google.com/appengine/docs)
### Language
[Python](https://www.python.org/)
## APIs
[Google Cloud Endpoints](https://developers.google.com/appengine/docs/python/endpoints/)

### Setup Instructions
1. Register in Google Developer Console,  create a new project.
2. In Credentials menu, create new Client ID and set the redirect URIs like that:
  ```
  https://your_projectID.appspot.com/oauth2callback
  http://localhost:8080/oauth2callback
  ```
3. Clone or download this project.
4. Update the value of application in app.yaml to your_projectID.
5. Update the value of WEB_CLIENT_ID  in  settings.py to the Client ID.
6. Update the value of CLIENT_ID in static/js/app.js to the Client ID.
7. Run at local:
  ```
  Run: "dev_appserver.py ." in your working folder in your terminal.
  
  Go to:
  localhost:8080/ (conference app with some limited UI)
  localhost:8000/ (admin server with Datastore Viewer)
  localhost:8080/_ah/api/explorer/ (APIs)
  ```
8. Deploy on Google server:
  ```
  Run: "appcfg.py --oauth2 update ." in your working folder in your terminal.
  
  Go to:
  https://your_projectID.appspot.com/ (conference app with some limited UI).
  https://apis-explorer.appspot.com/apis-explorer/?base=https://your_projectID.appspot.com/_ah/api#p/conference/v1/ (APIs)
  
  You can see the database in Google Developers Console (go to Storage/ Cloud DataStore/ Query).
  
  In either cases, you can add new entities to the database manually or via the APIs functions in the program, 
  and you can see all of them in Datastore Viewer.
  
  ```

