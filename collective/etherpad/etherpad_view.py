import time
import logging
from Products.Five.browser import BrowserView
from Products.CMFCore import permissions
from zope import component, i18nmessageid
from zope import schema
from plone.registry.interfaces import IRegistry
from collective.etherpad.settings import EtherpadEmbedSettings
from collective.etherpad.settings import EtherpadSettings
from collective.etherpad.api import HTTPAPI, get_pad_id
from plone.uuid.interfaces import IUUID
from Products.CMFCore.utils import getToolByName
from urllib import urlencode
from Products.CMFPlone import PloneMessageFactory
from Products.CMFCore.utils import _checkPermission
from Products.statusmessages.interfaces import IStatusMessage


logger = logging.getLogger('collective.etherpad')
_ = i18nmessageid.MessageFactory('collective.etherpad')
_p = PloneMessageFactory


class EtherpadView(BrowserView):
    """Implement etherpad for Archetypes content types"""

    def __init__(self, context, request):
        super(EtherpadView, self).__init__(context, request)
        self.context = context
        self.request = request

        self.etherpad = None
        self.embed_settings = None
        self.etherpad_settings = None
        self.portal_state = None
        self.portal_registry = None

        self.padID = None
        self.padName = None
        self.pads = []

        self.groupMapper = None
        self.groupID = None

        self.authorMapper = None
        self.authorName = None
        self.authorID = None

        self.sessionID = None
        self.validUntil = None

        self.etherpad_iframe_url = None

    def __call__(self):
        self.update()
        return self.index()

    def update(self):
        if self.portal_state is None:
            self.portal_state = component.getMultiAdapter(
                (self.context, self.request), name=u'plone_portal_state'
            )

        if self.portal_registry is None:
            self.portal_registry = component.getUtility(IRegistry)

        if self.embed_settings is None:
            self.embed_settings = {}
            registry = self.portal_registry
            self.embed_settings = registry.forInterface(EtherpadEmbedSettings)

        if self.etherpad_settings is None:
            registry = self.portal_registry
            self.etherpad_settings = registry.forInterface(EtherpadSettings)

        if self.etherpad is None:
            self.etherpad = HTTPAPI(self.context, self.request)
            self.etherpad.update()
            try:
                self.etherpad.checkToken()
            except ValueError:
                status = IStatusMessage(self.request)
                msg = _(u"Etherpad connection error")
                status.add(msg)
                self.etherpad_iframe_url = ""
                return
        self._updateName()
        self._updateAuthor()
        self._updateId()
        self._updateSession()
        self._updateIframe()

    def _updateName(self):
        if self.padName is None:
            self.padName = IUUID(self.context)
            logger.debug('set padName to %s' % self.padName)
        if self.groupMapper is None:
            self.groupMapper = self.padName

    def _updateAuthor(self):
        #Portal maps the internal userid to an etherpad author.
        if self.authorMapper is None:
            mt = getToolByName(self.context, 'portal_membership')
            member = mt.getAuthenticatedMember()
            if member is not None:
                self.authorMapper = member.getId()
                if self.authorName is None:
                    self.authorName = member.getProperty("fullname")

        if self.authorID is None:
            author = self.etherpad.createAuthorIfNotExistsFor(
                authorMapper=self.authorMapper,
                name=self.authorName
            )
            if author:
                self.authorID = author['authorID']

    def _updateId(self):
        #Portal maps the internal userid to an etherpad group:
        if self.groupID is None:
            group = self.etherpad.createGroupIfNotExistsFor(
                groupMapper=self.groupMapper
            )
            if group:
                self.groupID = group['groupID']

        #Portal creates a pad in the userGroup
        if self.padID is None:
            self.padID = get_pad_id(self.groupID, self.padName)
            pads = self.etherpad.listPads(groupID=self.groupID)
            if not (pads and self.padID in pads.get(u"padIDs", [])):
                #create a pad and try to load text from field:
                if hasattr(self, 'getEtherpadField'):
                    field = self.getEtherpadField()
                    text = field.get(self.context)
                    ptransforms = getToolByName(
                        self.context, 'portal_transforms', None
                    )
                    if ptransforms and text:
                        text = ptransforms.convertTo('text/plain', text)._data
                    if text is None:
                        text = ""
                else:
                    text = ''
                self.etherpad.createGroupPad(
                    groupID=self.groupID,
                    padName=self.padName,
                    text=text,
                )

    def _updateSession(self):
        #Portal starts the session for the user on the group:
        if not self.validUntil:
            #24 hours in unix timestamp in seconds
            self.validUntil = str(int(time.time() + 24 * 60 * 60))

        if not self.sessionID:
            session = self.etherpad.createSession(
                groupID=self.groupID,
                authorID=self.authorID,
                validUntil=self.validUntil
            )
            if session:
                self.sessionID = session['sessionID']

            self._addSessionCookie()

    def _updateIframe(self):
        if self.etherpad_iframe_url is None:
            #TODO: made this configuration with language and stuff
            url = self.portal_state.portal_url()
            basepath = self.etherpad_settings.basepath
            query = {}  # self.embed_settings  # TODO: as dict
            for field in schema.getFields(EtherpadEmbedSettings):
                value = getattr(self.embed_settings, field)
                if value is not None:
                    query[field] = value

            query['lang'] = self.portal_state.language()
            equery = urlencode(query)
            equery = equery.replace('True', 'true').replace('False', 'false')
            url = "%s%sp/%s?%s" % (url, basepath, self.padID, equery)
            self.etherpad_iframe_url = url

    @property
    def portal(self):
        """To be overloaded in unit tests"""
        if not getattr(self, '_portal', None):
            self._portal = self.portal_state.portal()

        return self._portal

    def _getBasePath(self):
        """In case we are behind a proxy or if VHM remap our
        urls, take care to remap the cookie basepath too"""
        padvpath = "/".join(
            self.request.physicalPathToVirtualPath(
                self.portal.getPhysicalPath()
            )
        )

        padvpath += self.etherpad_settings.basepath
        padvpath = padvpath.replace('//', '/')
        if not padvpath.startswith('/'):
            padvpath = '/' + padvpath

        return padvpath

    def _addSessionCookie(self):
        logger.debug('setCookie("sessionID", "%s")' % self.sessionID)
        self.request.response.setCookie(
            'sessionID',
            self.sessionID,
            quoted=False,
            path=self._getBasePath(),
        )

    def can_edit(self):
        return _checkPermission(permissions.ModifyPortalContent, self.context)

    def content(self):
        #get the content from etherpad
        html = self.etherpad.getHTML(padID=self.padID)
        if html and 'html' in html:
            return html["html"]

        return ""
