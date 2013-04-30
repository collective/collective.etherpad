# there are no import of archetypes in .archetypes just the way fields are
# retrieved
from z3c.form import button
from zope import schema
from zope.component import getUtility
from collective.etherpad import archetypes
from plone.app.textfield.interfaces import IRichText
from plone.dexterity.interfaces import IDexterityFTI


class EtherpadSyncForm(archetypes.EtherpadSyncForm):

    def __init__(self, context, request):
        super(EtherpadSyncForm, self).__init__(context, request)
        self.dexterity_fti = None


class EtherpadEditView(archetypes.EtherpadEditView):
    """Implement etherpad for Archetypes content types"""
    form_instance_class = EtherpadSyncForm

    def __init__(self, context, request):
        super(EtherpadEditView, self).__init__(context, request)
        self.dexterity_fti = None
        self.model = None

    def update(self):
        if self.dexterity_fti is None:
            self.dexterity_fti = getUtility(
                IDexterityFTI,
                name=self.context.portal_type
            )
        if self.model is None:
            self.model = self.dexterity_fti.lookupSchema()
        super(EtherpadEditView, self).update()

    def getEtherpadField(self):
        fields = schema.getFields(self.model)
        for name in fields:
            field = fields[name]
            if IRichText.providedBy(field):
                return field
