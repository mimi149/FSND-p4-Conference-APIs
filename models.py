#!/usr/bin/env python

"""models.py

Udacity conference server-side Python App Engine data & ProtoRPC models

$Id: models.py,v 1.1 2014/05/24 22:01:10 wesc Exp $

created/forked from conferences.py by wesc on 2014 may 24

"""

__author__ = 'wesc+api@google.com (Wesley Chun)'

import httplib
import endpoints
from protorpc import messages
from google.appengine.ext import ndb
from validate_email import validate_email
import re

class Profile(ndb.Model):
    """ Profile -- User profile object."""

    displayName = ndb.StringProperty()
    mainEmail = ndb.StringProperty()
    teeShirtSize = ndb.StringProperty(default='NOT_SPECIFIED')
    conferenceKeysToAttend = ndb.StringProperty(repeated=True)
    wishlistOfSessionKeys = ndb.StringProperty(repeated=True)

# needed for conference registration
class BooleanMessage(messages.Message):
    """ BooleanMessage -- outbound Boolean value message."""

    data = messages.BooleanField(1)

class ConflictException(endpoints.ServiceException):
    """ ConflictException -- exception mapped to HTTP 409 response."""

    http_status = httplib.CONFLICT

class ProfileMiniForm(messages.Message):
    """ ProfileMiniForm -- update Profile form message."""

    displayName = messages.StringField(1)
    teeShirtSize = messages.EnumField('TeeShirtSize', 2)

class ProfileForm(messages.Message):
    """ ProfileForm -- Profile outbound form message."""

    displayName = messages.StringField(1)
    mainEmail = messages.StringField(2)
    teeShirtSize = messages.EnumField('TeeShirtSize', 3)

class TeeShirtSize(messages.Enum):
    """ TeeShirtSize -- t-shirt size enumeration value."""

    NOT_SPECIFIED = 1
    XS_M = 2
    XS_W = 3
    S_M = 4
    S_W = 5
    M_M = 6
    M_W = 7
    L_M = 8
    L_W = 9
    XL_M = 10
    XL_W = 11
    XXL_M = 12
    XXL_W = 13
    XXXL_M = 14
    XXXL_W = 15

class Speaker(ndb.Model):
    """ Speaker -- Speaker object."""

    name            = ndb.StringProperty(required=True)
    phones          = ndb.StringProperty(repeated=True)
    emails          = ndb.StringProperty(repeated=True)
    website         = ndb.StringProperty()
    company         = ndb.StringProperty()
    sessions        = ndb.KeyProperty(kind='Session', repeated=True)

    def __init__(self, *args, **kwds):
        super(Speaker, self).__init__(*args, **kwds)
        self._validate() # call my own validation here!

    def _validate(self):
        """ Validate phones and emails properties. Currentlly, US phone pattern and usual email pattern 
            are accepted. This code doesn't check if the host has SMTP Server or the email really exists."""

        if self.phones != []:
            p = re.compile('(\+?)([0-9]{1,2})(-)([0-9]{3})(-)([0-9]{3})(-)([0-9]{4}$)')
            for phone in self.phones:
                if p.match(phone) == None:
                    raise endpoints.BadRequestException("Phone number must be (+)(X)X-XXX-XXX-XXXX.")
    
        if self.emails != []:
            for email in self.emails:
                if validate_email(email) == None:
                    raise endpoints.BadRequestException("Invalid email.")
                    
  
class SpeakerForm(messages.Message):
    """ SpeakerForm -- Speaker outbound form message."""

    name            = messages.StringField(1, required=True)
    phones          = messages.StringField(2, repeated=True)
    emails          = messages.StringField(3, repeated=True)
    website         = messages.StringField(4)
    company         = messages.StringField(5)
    sessions        = messages.StringField(6, repeated=True)
    websafeKey      = messages.StringField(7)

class SpeakerForms(messages.Message):
    """ SpeakerForms -- multiple Speaker outbound form message."""

    items = messages.MessageField(SpeakerForm, 1, repeated=True)
    
class Conference(ndb.Model):
    """ Conference -- Conference object."""

    name            = ndb.StringProperty(required=True)
    description     = ndb.StringProperty()
    topics          = ndb.StringProperty(repeated=True)
    city            = ndb.StringProperty()
    startDate       = ndb.DateProperty()
    month           = ndb.IntegerProperty()
    endDate         = ndb.DateProperty()
    maxAttendees    = ndb.IntegerProperty()
    seatsAvailable  = ndb.IntegerProperty()
    organizerUserId = ndb.StringProperty()

class ConferenceForm(messages.Message):
    """ ConferenceForm -- Conference outbound form message."""

    name            = messages.StringField(1)
    description     = messages.StringField(2)
    topics          = messages.StringField(3, repeated=True)
    city            = messages.StringField(4)
    startDate       = messages.StringField(5)
    month           = messages.IntegerField(6)
    maxAttendees    = messages.IntegerField(7)
    seatsAvailable  = messages.IntegerField(8)
    endDate         = messages.StringField(9)
    websafeKey      = messages.StringField(10)
    organizerUserId = messages.StringField(11)
    organizerDisplayName= messages.StringField(12)
    
class ConferenceForms(messages.Message):
    """ ConferenceForms -- multiple Conference outbound form message."""

    items = messages.MessageField(ConferenceForm, 1, repeated=True)

class QueryForm(messages.Message):
    """ QueryForm -- Conference or session query inbound form message."""

    field = messages.StringField(1)
    operator = messages.StringField(2)
    value = messages.StringField(3)

class QueryProblemForm(messages.Message):
    """ QueryProblemForm in final project rubric."""

    startTime = messages.StringField(1)
    typeOfSession = messages.StringField(2)

class QueryForms(messages.Message):
    """ QueryForms -- multiple QueryForm inbound form message."""

    filters = messages.MessageField(QueryForm, 1, repeated=True)

class StringMessage(messages.Message):
    """ StringMessage-- outbound (single) string message."""

    data = messages.StringField(1, required=True)

class Session(ndb.Model):
    """ Session -- Session object."""

    name            = ndb.StringProperty(required=True)
    highlights      = ndb.StringProperty()
    typeOfSession   = ndb.StringProperty()
    date            = ndb.DateTimeProperty()
    startTime       = ndb.DateTimeProperty()
    endTime         = ndb.DateTimeProperty()
    location        = ndb.StringProperty()
    speaker         = ndb.KeyProperty(kind='Speaker', required=True)

class SessionForm(messages.Message):
    """ SessionForm -- Session outbound form message."""

    name            = messages.StringField(1)
    highlights      = messages.StringField(2)
    duration        = messages.StringField(3)
    typeOfSession   = messages.StringField(4)
    date            = messages.StringField(5)
    startTime       = messages.StringField(6)
    endTime         = messages.StringField(7)
    location        = messages.StringField(8)
    speakerKey      = messages.StringField(9)
    websafeKey      = messages.StringField(10)
    
class SessionForms(messages.Message):
    """ SessionForms -- multiple Session outbound form message."""

    items = messages.MessageField(SessionForm, 1, repeated=True)

class IntervalForm(messages.Message):
    """ IntervalForm -- time interval outbound form message. """

    fromDate        = messages.StringField(1)
    toDate          = messages.StringField(2)

class IntervalForms(messages.Message):
    """ IntervalForms -- time intervals outbound form message."""

    items = messages.MessageField(IntervalForm, 1, repeated=True)
