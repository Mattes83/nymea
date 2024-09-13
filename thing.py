"""Support for things."""

from __future__ import annotations

from .maveo_box import MaveoBox


class Thing:
    """Represents a thing connected to the maveo box."""

    def __init__(
        self,
        thingid: str,
        thingclassId: str,
        manufacturer: str,
        name: str,
        maveoBox: MaveoBox,
    ) -> None:
        """Init sensor."""
        self._id = thingid
        self.thingclass_id = thingclassId
        self.name = name
        self.manufacturer = manufacturer
        self.maveoBox = maveoBox

    @property
    def id(self) -> str:
        """Return ID for thing."""
        return self._id

    @staticmethod
    async def add(maveoBox: MaveoBox):
        """Add all things connected to the maveo box."""
        things = maveoBox.send_command("Integrations.GetThings")["params"]["things"]

        for thing in things:
            params = {}
            params["thingClassIds"] = [thing["thingClassId"]]
            thingClasses = maveoBox.send_command(
                "Integrations.GetThingClasses", params
            )["params"]["thingClasses"]

            vendors = maveoBox.send_command("Integrations.GetVendors")["params"][
                "vendors"
            ]

            vendor = next(x for x in vendors if x["id"] == thingClasses[0]["vendorId"])

            maveoBox.things.append(
                Thing(
                    thing["id"],
                    thing["thingClassId"],
                    vendor["displayName"],
                    thing["name"],
                    maveoBox,
                )
            )
