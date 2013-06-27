#python
import time
import logging
from urllib import urlencode

#zope
from Acquisition import aq_inner
from zope import component
from zope import interface
from zope import schema
from z3c.form import form, field, button
from zope import i18nmessageid

#cmf
from Products.CMFCore.utils import getToolByName

#plone
from plone.uuid.interfaces import IUUID
from plone.registry.interfaces import IRegistry
from Products.CMFPlone import PloneMessageFactory

#internal
from collective.etherpad.api import HTTPAPI
from collective.etherpad.settings import EtherpadEmbedSettings, EtherpadSettings
from plone.z3cform.layout import FormWrapper
from collective.etherpad.etherpad_view import EtherpadView

logger = logging.getLogger('collective.etherpad')
_ = i18nmessageid.MessageFactory('collective.etherpad')
_p = PloneMessageFactory


class EtherpadSyncForm(form.Form):
    fields = field.Fields(interface.Interface)

    def __init__(self, context, request):
        super(EtherpadSyncForm, self).__init__(context, request)
        self.etherpad = None
        self.padID = None
        self.field = None

    @button.buttonAndHandler(_p(u"Save"))
    def handleEtherpadToPlone(self, action):
        self.save()

    def save(self):
        #get the content from etherpad
        html = self.etherpad.getHTML(padID=self.padID)
        if html and 'html' in html:
            self.field.set(self.context, html['html'], mimetype='text/html')


class EtherpadEditView(EtherpadView, FormWrapper):
    """Implement etherpad for Archetypes content types"""
    form_instance_class = EtherpadSyncForm

    def __init__(self, context, request):
        super(EtherpadEditView, self).__init__(context, request)
        self.field = None
        self.form_instance = None

    def __call__(self):
        self.update()
        return self.index()

    def update(self):
        super(EtherpadEditView, self).update()
        if self.field is None:
            self.field = self.getEtherpadField()

        if self.form_instance is None:
            self.form_instance = self.form_instance_class(
                aq_inner(self.context), self.request
            )
            self.form_instance.__name__ = self.__name__
            self.form_instance.etherpad = self.etherpad
            self.form_instance.padID = self.padID
            self.form_instance.field = self.field
            FormWrapper.update(self)

    def getEtherpadField(self):
        return self.context.getPrimaryField()
