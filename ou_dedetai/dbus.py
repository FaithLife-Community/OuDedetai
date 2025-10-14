"""DBus listener"""

from dbus_next.service import ServiceInterface, method
from dbus_next.aio.message_bus import MessageBus

from ou_dedetai.app import App
from ou_dedetai.logos import LogosManager

class FaithLifeAppInterface(ServiceInterface):
    def __init__(self, app: App):
        super().__init__("io.github.Faithlife_Community.OuDedetai.FaithLifeApp")
        self.app = app

    @method()
    def Launch(self, args: 'as') -> None: # type: ignore[valid-type]
        LogosManager(self.app).start(args)


async def main(app: App):
    """Main function for handling dbus messages"""
    bus = await MessageBus().connect()
    interface = FaithLifeAppInterface(app)
    bus.export('/io/github/Faithlife_Community/OuDedetai', interface)
    # We may or may not get this name, continue anyways.
    await bus.request_name('io.github.Faithlife_Community.OuDedetai')
