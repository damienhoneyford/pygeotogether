"""Contains the main Geo Together functionality."""
from typing import List

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientError

from .geocommon import GeoEnergyType, GeoLivePowerUsage, GeoPeriodicEnergyUsage, GeoEnergyUsage, \
                       GeoTimePeriod
from .geocommon import GeoTogetherAuthenticationError, GeoTogetherError, GeoTogetherSystemError

def _build_url(uri: str) -> str:
    """Builds a fully-qualified URL from the given URI."""
    return "".join(["https://api.geotogether.com/", uri])

def _parse_historic_commodity_totals(
        time_period: GeoTimePeriod,
        commodity_totals: dict,
        accumulator: dict[GeoTimePeriod, GeoEnergyUsage]
    ):

    for usage in commodity_totals:
        energy_type = GeoEnergyType[usage["commodityType"]]
        amount = usage["energyKWh"] if "energyKWh" in usage else 0
        cost = usage["costPence"] if "costPence" in usage else 0
        if energy_type in accumulator:
            energy_usage = accumulator[energy_type]
            energy_usage._energy_amount += amount
            energy_usage._energy_cost += cost
        else:
            accumulator[energy_type] = GeoEnergyUsage(time_period, energy_type, amount, cost)

def _parse_current_costs(energy_type: GeoEnergyType, current_costs: dict,
                         accumulator: dict[GeoEnergyType, GeoPeriodicEnergyUsage]):
    usage = [
        GeoEnergyUsage(
            GeoTimePeriod[u["duration"]],
            energy_type,
            u["energyAmount"],
            u["costAmount"]
        ) for u in current_costs
    ]
    if energy_type in accumulator:
        _periodic_usage = accumulator[energy_type] + usage
    else:
        accumulator[energy_type] = GeoPeriodicEnergyUsage(
            energy_type,
            usage
        )

def _parse_bill_to_date(bill_to_date: dict,
                        accumulator: dict[GeoEnergyType, GeoPeriodicEnergyUsage]):
    for unbilled in bill_to_date:
        energy_type = GeoEnergyType[unbilled["commodityType"]]
        usage = GeoEnergyUsage(
            GeoTimePeriod.UNBILLED,
            energy_type,
            None,
            unbilled["billToDate"]
        )
        if energy_type in accumulator:
            _periodic_usage = accumulator[energy_type] + usage
        else:
            accumulator[energy_type] = GeoPeriodicEnergyUsage(
                energy_type, [usage]
            )

def _parse_total_consumption(total_consumption: dict,
                             accumulator: dict[GeoEnergyType, GeoPeriodicEnergyUsage]):
    for consumption in total_consumption:
        energy_type = GeoEnergyType[consumption["commodityType"]]
        usage = GeoEnergyUsage(
            GeoTimePeriod.FOREVER,
            energy_type,
            consumption["totalConsumption"],
            None
        )
        if energy_type in accumulator:
            _periodic_usage = accumulator[energy_type] + usage
        else:
            accumulator[energy_type] = GeoPeriodicEnergyUsage(
                energy_type, [usage]
            )

class GeoTogetherClient:
    """Class to retrieve energy data from Geo Together devices."""

    def __init__(self, username: str, password: str, client_session: ClientSession = None) -> None:
        """Initialises GeoTogether class."""

        self._system_id = None
        self._username = username
        self._password = password
        if client_session:
            self._client_session = client_session
            self._owns_client_session = False
        else:
            self._client_session = ClientSession()
            self._owns_client_session = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, _exc_type, _exc, _traceback):
        if self._owns_client_session:
            await self._client_session.close()

    def _check_prerequisits(self):
        """Checks for necessary Authorization and System ID before calling a data API."""

        if "Authorization" not in self._client_session.headers:
            raise GeoTogetherAuthenticationError(
                "You must authenticate before you can use this API"
            )
        if not self._system_id:
            raise GeoTogetherSystemError(
                "You must resolve the system before you can use this API"
            )

    async def authenticate(self) -> bool:
        """Authenticates with the Geo Together API."""
        try:
            async with self._client_session.post(_build_url("usersservice/v2/login"), json = {
                "identity": self._username,
                "password": self._password,
            }) as response:

                if response.status == 200:
                    auth_payload = await response.json()

                    if "accessToken" in auth_payload:
                        self._client_session.headers["Authorization"] = (
                            f"Bearer {auth_payload['accessToken']}"
                        )
                        return True
        except ClientError:
            pass
        return False

    async def resolve_system(self, name: str = None) -> bool:
        """
        Resolves the ID of the Geo device with the given name,
        or the first device returned if no name is given.
        """
        try:
            uri = "api/userapi/v2/user/detail-systems?systemDetails=true"
            async with self._client_session.get(_build_url(uri)) as response:
                if response.status == 200:
                    device_details_payload = await response.json()

                    if "systemDetails" in device_details_payload:
                        for system in device_details_payload["systemDetails"]:
                            if "systemId" in system and "name" in system:
                                if (not name) or system["name"] == name:
                                    self._system_id = system["systemId"]
                                    break
        except ClientError:
            return False

        return self._system_id

    async def get_live_usage(self) -> List[GeoLivePowerUsage]:
        """Retrieves a snapshot of current power usage for all available energy types."""

        self._check_prerequisits()
        rtn = []
        try:
            uri = f"api/userapi/system/smets2-live-data/{self._system_id}"
            async with self._client_session.get(_build_url(uri)) as response:

                if response.status == 200:
                    usage_payload = await response.json()

                    if "power" in usage_payload and usage_payload["power"]:
                        rtn = [GeoLivePowerUsage(p) for p in usage_payload["power"]]
                elif response.status == 401:
                    del self._client_session.headers["Authorization"]
                    raise GeoTogetherAuthenticationError("Authentication has expired")
                else:
                    raise GeoTogetherError(
                        f"The Geo Together API call failed with status {response.status}"
                    )
        except ClientError as exc:
            raise GeoTogetherError("Connectivity Error") from exc
        return rtn

    async def get_periodic_usage(self) -> list[GeoPeriodicEnergyUsage]:
        """Retrieves the current energy usage for all available energy types."""

        self._check_prerequisits()
        rtn: dict[GeoEnergyType, GeoPeriodicEnergyUsage] = {}
        try:
            uri = f"api/userapi/system/smets2-periodic-data/{self._system_id}"
            async with self._client_session.get(_build_url(uri)) as response:

                if response.status == 200:
                    usage_payload = await response.json()

                    if "totalConsumptionList" in usage_payload:
                        _parse_total_consumption(usage_payload["totalConsumptionList"], rtn)
                    if "billToDateList" in usage_payload:
                        _parse_bill_to_date(usage_payload["billToDateList"], rtn)
                    if "currentCostsElec" in usage_payload:
                        _parse_current_costs(GeoEnergyType.ELECTRICITY,
                                             usage_payload["currentCostsElec"], rtn)
                    if "currentCostsGas" in usage_payload:
                        _parse_current_costs(GeoEnergyType.GAS_ENERGY,
                                             usage_payload["currentCostsGas"], rtn)
                elif response.status == 401:
                    del self._client_session.headers["Authorization"]
                    raise GeoTogetherAuthenticationError("Authentication has expired")
                else:
                    raise GeoTogetherError(
                        f"The Geo Together API call failed with status {response.status}"
                    )
        except ClientError as exc:
            raise GeoTogetherError("Connectivity Error") from exc
        return rtn.values()

    async def get_historic_usage(self, time_period: GeoTimePeriod, offset: int = 0)\
        -> list[GeoEnergyUsage]:

        """
        Retrieves historic energy usage for all available energy types.
        """
        self._check_prerequisits()
        if time_period is GeoTimePeriod.UNBILLED or time_period is GeoTimePeriod.FOREVER:
            raise GeoTogetherError(f"Cannot get historic usage for {time_period.value},"\
                "use get_periodic_usage instead")
        if offset > 0:
            offset *= -1
        rtn: dict[GeoTimePeriod, GeoEnergyUsage] = {}
        try:
            time_period_dates = time_period.resolve(offset)
            history_type = 'day' if time_period is GeoTimePeriod.MONTH else time_period.name.lower()
            uri = f"api/userapi/system/smets2-historic-{history_type}/{self._system_id}"\
                f"?from={time_period_dates[0].isoformat()}"\
                f"&to={time_period_dates[1].isoformat()}"

            async with self._client_session.get(_build_url(uri)) as response:

                if response.status == 200:
                    usage_payload = await response.json()

                    if "totalsList" in usage_payload:
                        for period_total in usage_payload["totalsList"]:
                            if "commodityTotalsList" in period_total:
                                _parse_historic_commodity_totals(
                                    time_period, period_total["commodityTotalsList"], rtn
                                )
        except ClientError as exc:
            raise GeoTogetherError("Connectivity Error") from exc

        return rtn.values()
