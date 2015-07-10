#!/usr/bin/env python

"""
conference.py -- Udacity conference server-side Python App Engine API;
    uses Google Cloud Endpoints
$Id: conference.py,v 1.25 2014/05/24 23:42:19 wesc Exp wesc $
created by wesc on 2014 apr 21
"""
__author__ = 'wesc+api@google.com (Wesley Chun)'

from datetime import datetime, timedelta
from sets import Set

import endpoints

from protorpc import messages
from protorpc import message_types
from protorpc import remote

from google.appengine.ext import ndb
from google.appengine.api import memcache
from google.appengine.api import taskqueue

from models import Profile
from models import ProfileMiniForm
from models import ProfileForm
from models import TeeShirtSize

from models import Conference
from models import ConferenceForm
from models import ConferenceForms
from models import QueryForm
from models import QueryForms
from models import QueryProblemForm

from models import Session
from models import SessionForm
from models import SessionForms

from models import IntervalForm
from models import IntervalForms

from models import Speaker
from models import SpeakerForm
from models import SpeakerForms

from models import BooleanMessage
from models import ConflictException
from models import StringMessage

from utils import getUserId, currentUser, duration

from settings import WEB_CLIENT_ID

EMAIL_SCOPE = endpoints.EMAIL_SCOPE
API_EXPLORER_CLIENT_ID = endpoints.API_EXPLORER_CLIENT_ID

MEMCACHE_ANNOUNCEMENTS_KEY = "RECENT_ANNOUNCEMENTS"
MEMCACHE_FEATURED_SPEAKER_KEY = "FEATURED_SPEAKER"

GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey = messages.StringField(1),
)

SESS_POST_REQUEST_BY_CONFERENCE_WEBSAFEKEY = endpoints.ResourceContainer(
    SessionForm,
    websafeKey = messages.StringField(1),
)

GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY_AND_TYPE_OF_SESSION = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey = messages.StringField(1),
    typeOfSession = messages.StringField(2),
)

GET_REQUEST_BY_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    speaker = messages.StringField(1),
)

GET_REQUEST_BY_SESSION_WEBSAFEKEY = endpoints.ResourceContainer(
    message_types.VoidMessage,
    websafeKey = messages.StringField(1),
)

GET_REQUEST_FOR_SPARE_TIME_FOR_SPEAKER = endpoints.ResourceContainer(
    message_types.VoidMessage,
    month = messages.IntegerField(1),
    year  = messages.IntegerField(2),
    speakerKey = messages.StringField(3),
)

CONF_POST_REQUEST = endpoints.ResourceContainer(
    ConferenceForm,
    websafeKey=messages.StringField(1),
)

CONFERENCE_DEFAULTS = {
    "city": "Default City",
    "maxAttendees": 0,
    "seatsAvailable": 0,
    "topics": [ "Default", "Topic" ],
}

SESSION_DEFAULTS = {
    "typeOfSession": "Keynote",
    "date": "2015-01-01",
    "startTime": "08:00:00",
    "endTime": "08:30:00",
}

OPERATORS = {
            'EQ':   '=',
            'GT':   '>',
            'GTEQ': '>=',
            'LT':   '<',
            'LTEQ': '<=',
            'NE':   '!='
            }

CONFERENCE_FIELDS = {
                    'NAME': 'name',
                    'CITY': 'city',
                    'TOPIC': 'topics',
                    'MONTH': 'month',
                    'MAX_ATTENDEES': 'maxAttendees',
                    'TYPE_OF_SESSION': 'typeOfSession',
                    'SEATS_AVAILABLE': 'seatsAvailable',
                    'START_DATE': 'startDate',
                    'END_DATE': 'endDate',
                    }

SESSION_FIELDS = {
                'NAME': 'name',
                'SPEAKER': 'speaker',
                'TYPE_OF_SESSION': 'typeOfSession',
                'DATE': 'date',
                'START_TIME': 'startTime',
                'END_TIME': 'endTime',
                'LOCATION': 'location',
                }

# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - 

@endpoints.api( name='conference',
                version='v1',
                allowed_client_ids=[WEB_CLIENT_ID, API_EXPLORER_CLIENT_ID],
                scopes=[EMAIL_SCOPE])
class ConferenceApi(remote.Service):
    """ Conference API v0.1"""

# - - - Profile objects - - - - - - - - - - - - - - - - - - - - - - - - 

    def _copyProfileToForm(self, profile):
        """ Copy relevant fields from Profile to ProfileForm."""

        profileForm = ProfileForm()
        for field in profileForm.all_fields():
            if hasattr(profile, field.name):
                # convert t-shirt string to Enum; just copy others
                if field.name == 'teeShirtSize':
                    setattr(profileForm, field.name, getattr(TeeShirtSize, 
                                                     getattr(profile, field.name)))
                else:
                    setattr(profileForm, field.name, getattr(profile, field.name))
        profileForm.check_initialized()
        return profileForm

    def _getProfileFromUser(self):
        """ Return user Profile from datastore, creating new one if non-existent."""

        user = endpoints.get_current_user()
        if not user:
            raise endpoints.UnauthorizedException('Authorization required')

        # get profile from datastore
        userId = getUserId(user)
        profileKey = ndb.Key(Profile, userId)
        profile = profileKey.get()
        # create new Profile if not there
        if not profile:
            profile = Profile(
                key = profileKey,
                displayName = user.nickname(),
                mainEmail= user.email(),
                teeShirtSize = str(TeeShirtSize.NOT_SPECIFIED),
            )
            profile.put()
        return profile

    def _doProfile(self, save_request=None):
        """ Get user profile and return to user, possibly updating it first."""

        # get user profile
        profile = self._getProfileFromUser()

        # if save_request, process user-modifyable fields
        if save_request:
            for field in ('displayName', 'teeShirtSize'):
                if hasattr(save_request, field):
                    val = getattr(save_request, field)
                    if val:
                        setattr(profile, field, str(val))
                        profile.put()

        # return ProfileForm
        return self._copyProfileToForm(profile)

    @endpoints.method(message_types.VoidMessage, ProfileForm,
                        path='profile', 
                        http_method='GET', 
                        name='getProfile')
    def getProfile(self, request):
        """ Return user profile."""
        return self._doProfile()

    @endpoints.method(ProfileMiniForm, ProfileForm,
                        path='profile', 
                        http_method='POST', 
                        name='saveProfile')
    def saveProfile(self, request):
        """ Update & return user profile."""
        return self._doProfile(request)

# - - - Speaker objects - - - - - - - - - - - - - - - - - - - - - - - -

    def _createSpeakerObject(self, request):
        """ Create or update Speaker object, returning SpeakerForm/request."""

        # copy SpeakerForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']

        # allocate new Speaker ID
        speakerId = Speaker.allocate_ids(size=1)[0]
        # make Speaker key from ID
        speakerKey = ndb.Key(Speaker, speakerId)
        data['key'] = speakerKey

        # create Speaker
        Speaker(**data).put()
        return self._copySpeakerToForm(speakerKey.get())

    def _copySpeakerToForm(self, speaker):
        """ Copy relevant fields from speaker to SpeakerForm."""

        speakerForm = SpeakerForm()
        for field in speakerForm.all_fields():
            if hasattr(speaker, field.name):
                # Process the list of session keys in speaker
                if field.name == "sessions":
                    sessionKeys = getattr(speaker, field.name)
                    sessions = []
                    for sessionKey in sessionKeys:
                        session = sessionKey.get()
                        if session:
                            sessions.append(session.key.urlsafe())
                    setattr(speakerForm, field.name, sessions)

                else:
                    setattr(speakerForm, field.name, getattr(speaker, field.name))

            elif field.name == "websafeKey":
                setattr(speakerForm, field.name, speaker.key.urlsafe())

        speakerForm.check_initialized()
        return speakerForm

    @endpoints.method(SpeakerForm, SpeakerForm, 
                        path='speaker',
                        http_method='POST', 
                        name='createSpeaker')
    def createSpeaker(self, request):
        """ Create a new Speaker."""
        return self._createSpeakerObject(request)

    @endpoints.method(message_types.VoidMessage, SpeakerForms,
                        path='querySpeakers',
                        http_method='POST',
                        name='querySpeakers')
    def querySpeakers(self, request):
        """Query for all speakers."""
        
        speakers = Speaker.query()

        # return individual SpeakerForm object per Speaker
        return SpeakerForms(
                items=[self._copySpeakerToForm(speaker) for speaker in speakers]
        )
# - - - Conference objects - - - - - - - - - - - - - - - - - - - - - - - 

    def _createConferenceObject(self, request):
        """Create a Conference object, returning ConferenceForm/request."""

        if not request.name:
            raise endpoints.BadRequestException("Conference 'name' field required")

        # preload necessary data items
        user, userId, userDisplayName, profileKey = currentUser()

        # copy ConferenceForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}
        del data['websafeKey']
        del data['organizerDisplayName']

        # add default values for those missing (both data model & outbound Message)
        for df in CONFERENCE_DEFAULTS:
            if data[df] in (None, []):
                data[df] = CONFERENCE_DEFAULTS[df]
                setattr(request, df, CONFERENCE_DEFAULTS[df])

        # convert dates from strings to Date objects; set month based on start_date
        if data['startDate']:
            data['startDate'] = datetime.strptime(data['startDate'][:10], "%Y-%m-%d").date()
            data['month'] = data['startDate'].month
        else:
            data['month'] = 0
        if data['endDate']:
            data['endDate'] = datetime.strptime(data['endDate'][:10], "%Y-%m-%d").date()

        # set seatsAvailable to be the same as maxAttendees on creation
        # both for data model & outbound Message
        if data["maxAttendees"] > 0:
            data["seatsAvailable"] = data["maxAttendees"]
            setattr(request, "seatsAvailable", data["maxAttendees"])

        # allocate new Conference ID with profileKey as parent
        conferenceId = Conference.allocate_ids(size=1, parent=profileKey)[0]

        # make Conference key from ID
        conferenceKey = ndb.Key(Conference, conferenceId, parent=profileKey)
        data['key'] = conferenceKey
        
        data['organizerUserId'] = request.organizerUserId = userId

        # create Conference, send email to organizer confirming
        # creation of Conference & return (modified) ConferenceForm
        Conference(**data).put()

        taskqueue.add(params={'email': user.email(),
            'conferenceInfo': repr(request)},
            url='/tasks/send_confirmation_email'
        )
        return self._copyConferenceToForm(conferenceKey.get(), userDisplayName)

    @ndb.transactional(xg=True)
    def _updateConferenceObject(self, request):

        # preload necessary data items
        user, userId, userDisplayName, profileKey = currentUser()

        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)
        
        # Verify if the user is the organizer of the conference
        if profileKey != conference.key.parent():
            raise endpoints.UnauthorizedException(
                "You must be the owner of the conference to update it.")    

        # update existing conference
        for field in request.all_fields():
            data = getattr(request, field.name)

            # only copy fields where we get data
            if data not in (None, []):
 
                # special handling for dates (convert string to Date)
                if field.name in ('startDate', 'endDate'):
                    data = datetime.strptime(data, "%Y-%m-%d").date()
                    if field.name == 'startDate':
                        conference.month = data.month

                setattr(conference, field.name, data)

        conference.put()
        return self._copyConferenceToForm(conference, userDisplayName)

    def _copyConferenceToForm(self, conference, displayName):
        """ Copy relevant fields from Conference to ConferenceForm."""

        conferenceForm = ConferenceForm()
        for field in conferenceForm.all_fields():
            if hasattr(conference, field.name):

                # convert Date to date string; just copy others
                if field.name.endswith('Date'):
                    setattr(conferenceForm, field.name, str(getattr(conference, field.name)))
                else:
                    setattr(conferenceForm, field.name, getattr(conference, field.name))

            elif field.name == "websafeKey":
                setattr(conferenceForm, field.name, conference.key.urlsafe())

            if displayName:
                setattr(conferenceForm, 'organizerDisplayName', displayName)

        conferenceForm.check_initialized()
        return conferenceForm

    @endpoints.method(ConferenceForm, ConferenceForm, 
                        path='conference',
                        http_method='POST', 
                        name='createConference')
    def createConference(self, request):
        """ Create a new conference."""
        return self._createConferenceObject(request)

    @endpoints.method(CONF_POST_REQUEST, ConferenceForm,
            path='conference/{websafeKey}',
            http_method='PUT', name='updateConference')
    def updateConference(self, request):
        """ Update a conference."""
        return self._updateConferenceObject(request)

# - - - - - - Session object - - - - - - - - - - - - - - - - - - - - - - 

    def _createSessionObject(self, request):
        """ Create or update Session object, returning SessionForm/request."""
        
        if not request.name:
            raise endpoints.BadRequestException("Session 'name' field required")

        # preload necessary data items
        user, userId, userDisplayName, profileKey = currentUser()
        
        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)
        
        # Verify if the user is the organizer of the conference
        if profileKey != conference.key.parent():
            raise endpoints.UnauthorizedException(
                "You must be the organizer of the conference to create its session.")    

        # copy SessionForm/ProtoRPC Message into dict
        data = {field.name: getattr(request, field.name) for field in request.all_fields()}

        # add default values for those missing (both data model & outbound Message)
        if data['startTime'] and not data['endTime']:
            data['endTime'] = data['startTime']
            
        for df in SESSION_DEFAULTS:
            if data[df] in (None, []):
                data[df] = SESSION_DEFAULTS[df]
                setattr(request, df, SESSION_DEFAULTS[df])
           
        # convert dates from strings to Date and Time objects;
        data['date'] = datetime.strptime(data['date'], "%Y-%m-%d")
        data['startTime'] = datetime.strptime(data['startTime'], "%H:%M:%S")
        data['endTime'] = datetime.strptime(data['endTime'], "%H:%M:%S")
        del data['speakerKey']
        del data['websafeKey']
        del data['duration']
            
        # allocate session's id by setting conference key as a parent
        sessionId = Session.allocate_ids(size = 1, parent = conferenceKey)[0]
        sessionKey = ndb.Key(Session, sessionId, parent = conferenceKey)
        data['key'] = sessionKey

        # Update the one to many relationship between speaker and session
        speaker, speakerKey = self._getSpeakerKey(request.speakerKey)
        data['speaker'] = speaker.key

        speaker.sessions.append(sessionKey)
        speaker.put()

        # create Session object and put it into DB
        Session(**data).put()
        
        # Call to set memcache about featured speakers
        self._setFeaturedSpeaker(speaker, conferenceKey)

        # return SessionForm object
        return self._copySessionToForm(sessionKey.get())

    def _setFeaturedSpeaker(self, speaker, conferenceKey):
        """ Setting featured speaker and sessions."""

        sessionsBySpeaker = ndb.get_multi(speaker.sessions)

        sessionsInSameConference = []
        for session in sessionsBySpeaker:
            if session.key.parent() == conferenceKey:
                sessionsInSameConference.append(session)

        if len(sessionsInSameConference) > 1:
            sessionNames = [session.name for session in sessionsInSameConference]
            featuredSpeakerText = speaker.name + ': ' + ', '.join(sessionNames)

            # set featuredSpeakerText in memcache
            memcache.set(MEMCACHE_FEATURED_SPEAKER_KEY, featuredSpeakerText)

    def _copySessionToForm(self, session):
        """ Copy relevant fields from Session to SessionForm."""

        sessionForm = SessionForm()

        for field in sessionForm.all_fields():
            if field.name == 'speakerKey':
                speaker = session.speaker.get()
                if speaker:
                    setattr(sessionForm, 'speakerKey', speaker.key.urlsafe())
            elif field.name == 'date':
                setattr(sessionForm, 'date', str(session.date.date()))
            elif field.name == 'startTime' :
                setattr(sessionForm, 'startTime', str(session.startTime.time()))
            elif field.name == 'endTime' :
                setattr(sessionForm, 'endTime', str(session.endTime.time()))
            elif field.name == 'duration' :
                setattr(sessionForm, 'duration', duration(session.startTime, session.endTime))
            elif field.name == "websafeKey":
                setattr(sessionForm, field.name, session.key.urlsafe())
            elif hasattr(session, field.name):
                setattr(sessionForm, field.name, getattr(session, field.name))             

        sessionForm.check_initialized()
        return sessionForm

    @endpoints.method(SESS_POST_REQUEST_BY_CONFERENCE_WEBSAFEKEY, SessionForm, 
                        path='createSession/{websafeKey}',
                        http_method='POST', 
                        name='createSession')
    def createSession(self, request):
        """ Create a new Session in a conference given by a websafeKey. 
            Open only to the organizer of that conference."""

        return self._createSessionObject(request)

# - - - User marks /unmarks session - - - - - - - - - - - - - - - - - - 

    def _addSessionToWishlist(self, request, mark = True):
        retval = None
        
        profile = self._getProfileFromUser() # get user Profile

        session, sessionKey = self._getSessionFromWebsafeKey(request.websafeKey)

        # user wants to mark this session
        if mark:
            # check if the session is already marked, otherwise add session to wishlist
            if request.websafeKey in profile.wishlistOfSessionKeys:
                raise ConflictException("You have already marked this session")

            profile.wishlistOfSessionKeys.append(request.websafeKey)
            retval = True

        # user wants to unmark this session
        else:
            # check if the session is marked, remove it
            if request.websafeKey in profile.wishlistOfSessionKeys:
                profile.wishlistOfSessionKeys.remove(request.websafeKey)
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        profile.put()
        return BooleanMessage(data=retval)

    @endpoints.method(GET_REQUEST_BY_SESSION_WEBSAFEKEY, BooleanMessage,
                        path='addSessionToWishlist/{websafeKey}',
                        http_method='POST', 
                        name='addSessionToWishlist')
    def addSessionToWishlist(self, request):
        """ Add a session given by a websafeKey to the user's list of sessions 
            they are interested in attending."""
        return self._addSessionToWishlist(request, True)

    @endpoints.method(GET_REQUEST_BY_SESSION_WEBSAFEKEY, BooleanMessage,
            path='removeSessionFromWishlist/{websafeKey}',
            http_method='POST', name='removeSessionFromWishlist')
    def removeSessionFromWishlist(self, request):
        """ Remove a session given by a websafeKey from the user's list of sessions
            they are interested in attending."""
        return self._addSessionToWishlist(request, False)

# - - - Query for conference  - - - - - - - - - - - - - - - - - - - - -

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                        path='getConferencesCreated',
                        http_method='POST', 
                        name='getConferencesCreated')
    def getConferencesCreated(self, request):
        """ Return conferences created by user."""
        
        user, userId, userDisplayName, userProfileKey = currentUser()

        conferences = Conference.query(ancestor = userProfileKey)

        # return set of ConferenceForm objects per Conference
        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, userDisplayName) for conf in conferences]
        )

    @endpoints.method(QueryForms, ConferenceForms,
                        path='queryConferences',
                        http_method='POST',
                        name='queryConferences')
    def queryConferences(self, request):
        """Query for all conferences.
            You can filter by these fields: NAME, CITY, TOPIC, MONTH, MAX_ATTENDEES, 
            SEATS_AVAILABLE, START_DATE, END_DATE,
            using these operators: EQ, GT, GTEQ, LT, LTEQ, NE."""
        
        conferences = self._getConferenceQuery(request)

        names = self._getOrganizerNames(conferences)
        
        # return individual ConferenceForm object per Conference
        return ConferenceForms(
                items=[self._copyConferenceToForm(conf, names[conf.organizerUserId]) 
                                                            for conf in conferences]
        )

    def _getOrganizerNames(self, conferences):
        
        # need to fetch organiser displayName from profiles
        # get all keys and use get_multi for speed
        organisers = [(ndb.Key(Profile, conf.organizerUserId)) for conf in conferences]
        profiles = ndb.get_multi(organisers)

        names = {}
        for profile in profiles:
            names[profile.key.id()] = profile.displayName
        return names

    def _getConferenceQuery(self, request):
        """ Return formatted query from the submitted filters."""

        q = Conference.query()

        # Check and format the filters
        inequality_filter, filters = self._checkAndFormatFilters(request.filters, "Conference")

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Conference.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Conference.name)

        return self._setFilters(q, filters)

# - - - Query for session - - - - - - - - - - - - - - - - - - - - - - - 

    @endpoints.method(GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY, SessionForms,
                        path = 'session/{websafeKey}',
                        http_method = 'POST',
                        name = 'getConferenceSessions')
    def getConferenceSessions(self, request):
        """ Given a websafeKey of a conference, query for all the sessions in it."""

        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)

        sessions = Session.query(ancestor = conferenceKey)

        # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(session) for session in sessions]
        )

    @endpoints.method(GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY_AND_TYPE_OF_SESSION, SessionForms,
                        path = 'session/{websafeKey}/{typeOfSession}',
                        http_method = 'POST',
                        name = 'getConferenceSessionsByType')                        
    def getConferenceSessionsByType(self, request):
        """ Given a websafeKey of a conference and a type of session, 
            return all sessions of that specified type and in that conference."""
        
        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)
        
        sessions = Session.query(Session.typeOfSession == request.typeOfSession)

        # return set of SessionForm objects per Session filtered by conferenceKey
        items=[sess.name for sess in sessions 
                                if (sess.key.parent() == conferenceKey)]

        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions 
                                if (sess.key.parent() == conferenceKey)]  
        )    

    @endpoints.method(message_types.VoidMessage, SessionForms,
                        path='getSessionsInWishlist',
                        http_method='GET', 
                        name='getSessionsInWishlist')
    def getSessionsInWishlist(self, request):
        """ Query for all the sessions the user is interested in."""
        profile = self._getProfileFromUser() # get user Profile

        sessionKeys = [ndb.Key(urlsafe=sKey) for sKey in profile.wishlistOfSessionKeys]
        sessions = ndb.get_multi(sessionKeys)

         # return set of SessionForm objects per Session
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions]       
        )

    @endpoints.method(GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY, SessionForms,
                        path='getSessionsOfAConferenceInWishlist/{websafeKey}',
                        http_method='POST', 
                        name='getSessionsOfAConferenceInWishlist')
    def getSessionsOfAConferenceInWishlist(self, request):
        """ Given a websafeKey of a conference, query for all the sessions in it that
            the user is interested in."""

        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)

        profile = self._getProfileFromUser() # get user Profile
        
        sessionKeys = [ndb.Key(urlsafe = sKey) for sKey in profile.wishlistOfSessionKeys]
        sessions = ndb.get_multi(sessionKeys)

        conferenceKey = ndb.Key(urlsafe = request.websafeKey)

        # return set of SessionForm objects per Session filtered by conferenceKey
        return SessionForms(
            items=[self._copySessionToForm(sess) for sess in sessions 
                                if (sess.key.parent() == conferenceKey)]  
        )    

    @endpoints.method(GET_REQUEST_BY_SPEAKER, SessionForms,
                        path='session_by_speaker/{speaker}',
                        http_method='POST', 
                        name='getSessionsBySpeaker')
    def getSessionsBySpeaker(self, request):
        """ Given a speaker, return all sessions given by this particular speaker, 
            across all conferences. """

        speaker, speakerKey = self._getSpeakerKey(request.speaker)

        sessions = ndb.get_multi(speaker.sessions)

        # return set of SessionForm objects per Session
        return SessionForms(items=[self._copySessionToForm(sess) for sess in sessions])
       
    @endpoints.method(QueryForms, SessionForms,
                        path='querySessions',
                        http_method='POST',
                        name='querySessions')
    def querySessions(self, request):
        """ Query for all sessions.
            You can filter by these fields: NAME, SPEAKER, TYPE_OF_SESSION, DATE, START_TIME, 
            END_TIME, LOCATION, using these operators: EQ, GT, GTEQ, LT, LTEQ, NE."""
        
        sessions = self._getSessionQuery(request)

        # return individual SessionForm object per Session
        return SessionForms(
                items=[self._copySessionToForm(sess) for sess in sessions]
        )
        
    def _getSessionQuery(self, request):
        """ Return formatted query from the submitted filters."""

        q = Session.query()
        
        # Check and format the filters
        inequality_filter, filters = self._checkAndFormatFilters(request.filters, "Session")

        # If exists, sort on inequality filter first
        if not inequality_filter:
            q = q.order(Session.name)
        else:
            q = q.order(ndb.GenericProperty(inequality_filter))
            q = q.order(Session.name)

        return self._setFilters(q, filters)

    def _setFilters(self, q, filters):   
        # Process filters and apply to q
        
        for filtr in filters:

            if filtr["field"] in ["startTime", "endTime"]:
                filtr["value"] = datetime.strptime(filtr["value"], "%H:%M:%S")

            if filtr["field"] in ["speaker"]:
                filtr["value"] = ndb.Key(urlsafe = filtr["value"])                
                
            if filtr["field"] in ["month", "maxAttendees", "seatsAvailable"]:
                filtr["value"] = int(filtr["value"])

            if filtr["field"] in ["startDate", "endDate", "date"]:
                # Change <type 'unicode'> to <type 'datetime.datetime'>
                filtr["value"] = datetime.strptime(filtr["value"], "%Y-%m-%d")
                
            if (filtr["field"] in ["startDate", "endDate", "date"]) and (filtr["operator"] == "="):
                # Equal filter for date type must be changed into two inequal filters
                formatted_query = ndb.query.FilterNode(filtr["field"], ">=", filtr["value"])
                q = q.filter(formatted_query)

                formatted_query = ndb.query.FilterNode(filtr["field"], "<", \
                                   ( filtr["value"] + timedelta(minutes = 1440)) )
                # use timedelta(minutes = 1440) in order to receive the type <datetime.datetime> 
                # for the calculated day, which is the same type of filtr["field"]
                q = q.filter(formatted_query)

            else: # For all other cases
                               
                formatted_query = ndb.query.FilterNode(filtr["field"], filtr["operator"], filtr["value"])
                q = q.filter(formatted_query)
        return q

    def _checkAndFormatFilters(self, filters, kind):
        """ Parse, check validity and format user supplied filters."""
        formatted_filters = []
        inequality_field = None
 
        for f in filters:   

            filtr = {field.name: getattr(f, field.name) for field in f.all_fields()}
            
            # Test for field name and operator
            try:
                if kind == "Session":
                    filtr["field"] = SESSION_FIELDS[filtr["field"]]
                elif kind == "Conference":
                    filtr["field"] = CONFERENCE_FIELDS[filtr["field"]]

                filtr["operator"] = OPERATORS[filtr["operator"]]
            except KeyError:
                raise endpoints.BadRequestException("Filter contains invalid field or operator")

            # Every operation except "=" is an inequality
            # Every filter for date type is inequal because even equal filter for 
            # date type must be changed into two inequal filters (will be implemented 
            # in _setFilters function), e.g. date1==date2 is equivalent to (date1 >= date2) 
            # and (date1 < date2 + 24 hours (e.g. 1440 minutes))
          
            if ((filtr["operator"] != "=") or
                (filtr["field"] in ["startDate", "endDate", "date"])):
                # Check if inequality operation has been used in previous filters
                # Disallow the filter if inequality was performed on a different field before
                # Track the field on which the inequality operation is performed
                if inequality_field and inequality_field != filtr["field"]:
                    raise endpoints.BadRequestException("Inequality filter is allowed on  \
                        only one field (Equality filter for date is considered as inequality)")
                else:
                    inequality_field = filtr["field"]

            formatted_filters.append(filtr)
        return (inequality_field, formatted_filters)

# - - - - Additional queries - - - - - - - - - - - - - - - - - - - - - - 
      
    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                        path='filterPlayground',
                        http_method='GET', 
                        name='filterPlayground')
    def filterPlayground(self, request):
        """ For trying some filters and indexes."""

        q = Conference.query()
        
        # simple filter usage:
        #q = q.filter(Conference.city == "London")
        #q = q.filter(Conference.topics == "Medical Innovations")
        #q = q.filter(Conference.maxAttendees > 10)
        #q = q.order(Conference.name)

        # advanced filter building and usage
        # field = "city"
        # operator = "="
        # value = "London"
        # f = ndb.query.FilterNode(field, operator, value)
        # q = q.filter(f)

        return ConferenceForms(
            items=[self._copyConferenceToForm(conf, "") for conf in q]
        )

    @endpoints.method(QueryProblemForm, SessionForms,
                        path='queryProblem',
                        http_method='POST',
                        name='queryProblem')
    def queryProblem(self, request):
        """ Query problem in final project rubric.
            Query for the sessions that start before request.startTime and 
            do not have type of session like request.typeOfSession."""
        
        if not request.startTime or not request.typeOfSession:
            raise endpoints.BadRequestException("'typeOfSession' and 'startTime' field required")

        startTime = datetime.strptime(request.startTime, "%H:%M:%S")

        # The solution is equivalent to:
        # q = Session.query(ndb.AND( (Session.startTime < startTime),
        #                            (Session.typeOfSession != request.typeOfSession) ))
        # but there are more than one inequality filter for more than one property,
        # which is rejected by Datastore. So we have to solve by python step by step.

        # sessions start before given time
        sessionsTime = Session.query(Session.startTime < startTime)

        # sessions have typeOfSession equal to given type
        sessionsType = Session.query(Session.typeOfSession == request.typeOfSession)

        sessions = []

        # select only the sessions having type not equal to given type of session
        for session in sessionsTime:
            if session not in sessionsType:
                sessions.append(session)
        
        # return individual SessionForm object per session
        return SessionForms(
                items=[self._copySessionToForm(session) for session in sessions]
        )

    def _additionalQuery1(self, month, year, speaker):
        """ Return the free intervals for a given speaker in a given month of a year."""

        # Get all the sessions given by the speaker
        sessionKeys = speaker.sessions
        sessionOfSpeaker = ndb.get_multi(sessionKeys)

        # busyDay will be a set of the days in this month and year 
        # when the speaker has his or her session.
        busyDay = Set()
        for session in sessionOfSpeaker:
            if (session.date.month == month) and (session.date.year == year):
                busyDay.add(session.date.day)
       
        if month in [1,3,5,7,8,10,12]:
            days = 31
        elif month == 2:
            days = 28
        else:
            days = 30

        # Get free intervals by eliminating busy days
        freeIntervals = []
        busyStatus = True
        for day in range(1,days +1):
            if busyStatus:
                if day not in busyDay:
                    busyStatus = False
                    startDate = str(day)
            else:
                if day in busyDay:
                    endDate = str(day -1)
                    freeIntervals.append((startDate, endDate))
                    busyStatus = True
        if not busyStatus:
            endDate = str(days)
            freeIntervals.append((startDate, endDate))
            
        return freeIntervals

    @endpoints.method(GET_REQUEST_FOR_SPARE_TIME_FOR_SPEAKER, IntervalForms,
                        path='additionalQuery1/{month}/{year}/{speakerKey}',
                        http_method='POST',
                        name='additionalQuery1')
    def additionalQuery1(self, request):
        """ Query for spare time intervals for a given speaker in a given month of a year."""
        
        if request.month not in range(1,13) or request.year not in range(1,3000):
            raise endpoints.BadRequestException("Invalid month or year")
        
        speaker, speakerKey = self._getSpeakerKey(request.speakerKey)

        freeIntervals = self._additionalQuery1(request.month, request.year, speaker)
        
        return IntervalForms(
            items = [IntervalForm(fromDate=interval[0], toDate=interval[1]) 
                                            for interval in freeIntervals]
        )
        
    @endpoints.method(IntervalForm, SessionForms,
                        path='additionalQuery2',
                        http_method='POST',
                        name='additionalQuery2')
    def additionalQuery2(self, request):
        """ Query for all the sessions of the seat-available conferences in a given time."""

        if (not request.fromDate) or (not request.toDate):
            raise endpoints.BadRequestException("'fromDate' and 'toDate' field required: YYYY-MM-DD")
        fromDate = datetime.strptime(request.fromDate, "%Y-%m-%d")
        toDate = datetime.strptime(request.toDate, "%Y-%m-%d")

        conferences = Conference.query(Conference.seatsAvailable > 0)
        conferenceKeys = [conf.key for conf in conferences]

        # filter by time
        sessions = Session.query(ndb.AND((Session.date >= fromDate),
                                         (Session.date <= toDate)
                                        )
                                )
 
        # filter by seat-available conference
        result = []
        for session in sessions:
            if session.key.parent() in conferenceKeys:
                result.append(session)
                
        return SessionForms(
                items=[self._copySessionToForm(session) for session in result]
        )

# - - - Registration/ unregistration for conference  - - - - - - - - - -

    @ndb.transactional(xg=True)
    def _conferenceRegistration(self, request, reg=True):
        """ Register or unregister user for selected conference."""

        retval = None
        profile = self._getProfileFromUser() # get user Profile

        conference, conferenceKey = self._getConferenceFromWebsafeKey(request.websafeKey)

        # register
        if reg:
            # check if user already registered otherwise add
            if request.websafeKey in profile.conferenceKeysToAttend:
                raise ConflictException("You have already registered for this conference")

            # check if seats avail
            if conference.seatsAvailable <= 0:
                raise ConflictException("There are no seats available.")

            # register user, take away one seat
            profile.conferenceKeysToAttend.append(request.websafeKey)
            conference.seatsAvailable -= 1
            retval = True

        # unregister
        else:
            # check if user already registered
            if request.websafeKey in profile.conferenceKeysToAttend:

                # unregister user, add back one seat
                profile.conferenceKeysToAttend.remove(request.websafeKey)
                conference.seatsAvailable += 1
                retval = True
            else:
                retval = False

        # write things back to the datastore & return
        profile.put()
        conference.put()
        return BooleanMessage(data = retval)

    @endpoints.method(GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY, BooleanMessage,
                        path='conference/{websafeKey}',
                        http_method='POST', 
                        name='registerForConference')
    def registerForConference(self, request):
        """ Register user for a conference given by a websafeKey."""
        return self._conferenceRegistration(request)

    @endpoints.method(GET_REQUEST_BY_CONFERENCE_WEBSAFEKEY, BooleanMessage,
                        path='conference/unregister/{websafeKey}',
                        http_method='POST', 
                        name='unregisterForConference')
    def unregisterForConference(self, request):
        """ Unregister user for a conference given by a websafeKey."""
        return self._conferenceRegistration(request, False)

    @endpoints.method(message_types.VoidMessage, ConferenceForms,
                        path='conferences/attending',
                        http_method='GET', 
                        name='getConferencesToAttend')
    def getConferencesToAttend(self, request):
        """ Get list of conferences that user has registered for."""

        profile = self._getProfileFromUser() # get user Profile

        # Get conferenceKeysToAttend from profile.
        
        conferenceKeysToAttend = [ndb.Key(urlsafe=key) 
                                    for key in profile.conferenceKeysToAttend]

        # Fetch conferences from datastore. 
        conferences = ndb.get_multi(conferenceKeysToAttend)
   
        names = self._getOrganizerNames(conferences)
            
        # return set of ConferenceForm objects per Conference
        return ConferenceForms(items=[self._copyConferenceToForm(conf, \
                                      names[conf.organizerUserId]) for conf in conferences]
        )
        
# - - - Announcements - - - - - - - - - - - - - - - - - - - - - - - - - 

    @staticmethod
    def _cacheAnnouncement():
        """ Create Announcement & assign to memcache; used by memcache cron job & 
            putAnnouncement()."""
        
        conferences = Conference.query(ndb.AND(
            Conference.seatsAvailable <= 5,
            Conference.seatsAvailable > 0)
        ).fetch(projection=[Conference.name])

        if conferences:
            # If there are almost sold out conferences,
            # format announcement and set it in memcache
            announcement = '%s %s' % (
                'Last chance to attend! The following conferences '
                'are nearly sold out:',
                ', '.join(conf.name for conf in conferences))
            memcache.set(MEMCACHE_ANNOUNCEMENTS_KEY, announcement)
        else:
            # If there are no sold out conferences,
            # delete the memcache announcements entry
            announcement = ""
            memcache.delete(MEMCACHE_ANNOUNCEMENTS_KEY)

        return announcement

    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/get',
            http_method='GET', name='getAnnouncement')
    def getAnnouncement(self, request):
        """ Return Announcement from memcache."""

        return StringMessage(data=memcache.get(MEMCACHE_ANNOUNCEMENTS_KEY) or "")

    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='conference/announcement/put',
            http_method='GET', name='putAnnouncement')
    def putAnnouncement(self, request):
        """ Put Announcement into memcache"""

        return StringMessage(data=self._cacheAnnouncement())

    @endpoints.method(message_types.VoidMessage, StringMessage,
            path='getFeaturedSpeaker',
            http_method='GET', name='getFeaturedSpeaker')
    def getFeaturedSpeaker(self, request):
        """ Returns featured speaker and sessions from memcache."""

        return StringMessage(data=memcache.get(MEMCACHE_FEATURED_SPEAKER_KEY) or "")

# - - - Auxiliary methods - - - - - - - - - - - - - - - - - - - - - - - 
# Often combine with validating when getting the required values

    def _getConferenceFromWebsafeKey(self, websafeKey):
        if websafeKey == None:
            raise endpoints.NotFoundException("You must enter a Conference Key.")

        conferenceKey = ndb.Key(urlsafe = websafeKey)
        conference = conferenceKey.get()

        # Verify if the websafeKey is of a Conference object
        if (not conference) or (type(conference).__name__ != "Conference"):
            raise endpoints.NotFoundException("Invalid Conference Key: %s" % websafeKey)    
        
        return conference, conferenceKey
      
        
    def _getSessionFromWebsafeKey(self, websafeKey):
        if websafeKey == None:
            raise endpoints.NotFoundException("You must enter a Session Key.")
            
        sessionKey = ndb.Key(urlsafe = websafeKey)
        session = sessionKey.get()

        # Verify if the websafeKey is of a Session object
        if (not session) or (type(session).__name__ != "Session"):
            raise endpoints.NotFoundException("Invalid Session Key: %s" % websafeKey)    
        
        return session, sessionKey   

    def _getSpeakerKey(self, key):
        if key == None:
            raise endpoints.NotFoundException("You must enter a Speaker Key.")

        speakerKey = ndb.Key(urlsafe = key)
        speaker = speakerKey.get()

        # Verify if the speakerKey is valid
        if (not speaker) or (type(speaker).__name__ != "Speaker"):
            raise endpoints.NotFoundException("Invalid Speaker Key: %s" % key)    
        
        return speaker, speakerKey   

# registers API
api = endpoints.api_server([ConferenceApi])
