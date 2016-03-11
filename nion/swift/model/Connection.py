"""
    Contains classes related to connections between library objects.
"""

# standard libraries
# None

# third party libraries
# None

# local libraries
from nion.swift.model import Region
from nion.ui import Binding
from nion.ui import Converter
from nion.ui import Observable
from nion.ui import Persistence


class Connection(Observable.Observable, Observable.Broadcaster, Persistence.PersistentObject):
    """ Represents a connection between two objects. """

    def __init__(self, type):
        super().__init__()
        self.define_type(type)
        self._closed = False

    def close(self):
        assert not self._closed
        self._closed = True

    def _property_changed(self, name, value):
        self.notify_set_property(name, value)


class PropertyConnection(Connection):
    """ Binds the properties of two objects together. """

    def __init__(self, source=None, source_property=None, target=None, target_property=None):
        super().__init__("property-connection")
        self.define_property("source_uuid", converter=Converter.UuidToStringConverter())
        self.define_property("source_property")
        self.define_property("target_uuid", converter=Converter.UuidToStringConverter())
        self.define_property("target_property")
        # these are only set in persistent object context changed
        self.__source = source
        self.__target = target
        self.__binding = None
        self.__target_property_changed_listener = None
        # suppress messages while we're setting source or target
        self.__suppress = False
        # but setup if we were passed objects
        if source is not None:
            self.source_uuid = source.uuid
        if source_property:
            self.source_property = source_property
        if target is not None:
            self.target_uuid = target.uuid
        if target_property:
            self.target_property = target_property

    def close(self):
        if self.__binding:
            self.__binding.close()
            self.__binding = None
        if self.__target_property_changed_listener:
            self.__target_property_changed_listener.close()
            self.__target_property_changed_listener = None
        super().close()

    def __set_target_from_source(self, value):
        if not self.__suppress:
            self.__suppress = True
            setattr(self.__target, self.target_property, value)
            self.__suppress = False

    def __set_source_from_target(self, value):
        if not self.__suppress:
            self.__suppress = True
            if self.__binding:
                self.__binding.update_source(value)
            self.__suppress = False

    def persistent_object_context_changed(self):
        """ Override from PersistentObject. """
        super().persistent_object_context_changed()

        def register():
            if self.__source is not None and self.__target is not None:
                self.__binding = Binding.PropertyBinding(self.__source, self.source_property)
                self.__binding.target_setter = self.__set_target_from_source
                self.__binding.update_target_direct(self.__binding.get_target_value())

        def source_registered(source):
            self.__source = source
            register()

        def target_registered(target):
            self.__target = target

            def property_changed(property_name, value):
                if property_name == self.target_property:
                    self.__set_source_from_target(value)

            assert self.__target_property_changed_listener is None
            self.__target_property_changed_listener = target.property_changed_event.listen(property_changed)
            register()

        def unregistered(source=None):
            if self.__binding:
                self.__binding.close()
                self.__binding = None
            if self.__target_property_changed_listener:
                self.__target_property_changed_listener.close()
                self.__target_property_changed_listener = None

        if self.persistent_object_context:
            self.persistent_object_context.subscribe(self.source_uuid, source_registered, unregistered)
            self.persistent_object_context.subscribe(self.target_uuid, target_registered, unregistered)
        else:
            unregistered()


class IntervalListConnection(Connection):
    """Binds the intervals on a buffered data source to the interval_descriptors on a line profile graphic.

    This is a one way connection from the data source to the line profile graphic.
    """

    def __init__(self, buffered_data_source=None, line_profile=None):
        super().__init__("interval-list-connection")
        self.define_property("source_uuid", converter=Converter.UuidToStringConverter())
        self.define_property("target_uuid", converter=Converter.UuidToStringConverter())
        # these are only set in persistent object context changed
        self.__source = buffered_data_source
        self.__target = line_profile
        self.__item_inserted_event_listener = None
        self.__item_removed_event_listener = None
        self.__interval_mutated_listeners = list()
        # but setup if we were passed objects
        if buffered_data_source is not None:
            self.source_uuid = buffered_data_source.uuid
        if line_profile is not None:
            self.target_uuid = line_profile.uuid

    def close(self):
        super().close()

    def persistent_object_context_changed(self):
        """ Override from PersistentObject. """
        super().persistent_object_context_changed()

        def detach():
            for listener in self.__interval_mutated_listeners:
                listener.close()
            self.__interval_mutated_listeners = list()

        def reattach():
            detach()
            interval_descriptors = list()
            if self.__source:
                for region in self.__source.regions:
                    if isinstance(region, Region.IntervalRegion):
                        interval_descriptor = {"interval": region.interval, "color": "#F00"}
                        interval_descriptors.append(interval_descriptor)
                        self.__interval_mutated_listeners.append(region.property_changed_event.listen(lambda k, v: reattach()))
            if self.__target:
                self.__target.interval_descriptors = interval_descriptors

        def item_inserted(key, value, before_index):
            if key == "region" and self.__target:
                reattach()

        def item_removed(key, value, index):
            if key == "region" and self.__target:
                reattach()

        def source_registered(source):
            self.__source = source
            self.__item_inserted_event_listener = self.__source.item_inserted_event.listen(item_inserted)
            self.__item_removed_event_listener = self.__source.item_removed_event.listen(item_removed)
            reattach()

        def target_registered(target):
            self.__target = target
            reattach()

        def unregistered(source=None):
            if self.__item_inserted_event_listener:
                self.__item_inserted_event_listener.close()
                self.__item_inserted_event_listener = None
            if self.__item_removed_event_listener:
                self.__item_removed_event_listener.close()
                self.__item_removed_event_listener = None

        if self.persistent_object_context:
            self.persistent_object_context.subscribe(self.source_uuid, source_registered, unregistered)
            self.persistent_object_context.subscribe(self.target_uuid, target_registered, unregistered)
        else:
            unregistered()


def connection_factory(lookup_id):
    build_map = {
        "property-connection": PropertyConnection,
        "interval-list-connection": IntervalListConnection,
    }
    type = lookup_id("type")
    return build_map[type]() if type in build_map else None
