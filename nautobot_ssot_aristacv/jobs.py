# pylint: disable=invalid-name,too-few-public-methods
"""Jobs for CloudVision integration with SSoT plugin."""
from grpc import RpcError

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse

from nautobot.extras.jobs import Job, BooleanVar
from nautobot.extras.models.tags import Tag
from nautobot.extras.models.customfields import CustomField

from nautobot_ssot.jobs.base import DataTarget, DataSource, DataMapping

from nautobot_ssot_aristacv.diffsync.tocv.cloudvision import CloudVision
from nautobot_ssot_aristacv.diffsync.tocv.nautobot import Nautobot

from nautobot_ssot_aristacv.diffsync.fromcv.cloudvision import CloudVision as C
from nautobot_ssot_aristacv.diffsync.fromcv.nautobot import Nautobot as N

from nautobot_ssot_aristacv.diffsync.fromcv.models import (
    DEFAULT_SITE,
    DEFAULT_DEVICE_ROLE,
    DEFAULT_DEVICE_ROLE_COLOR,
    DEFAULT_DEVICE_STATUS,
    DEFAULT_DEVICE_STATUS_COLOR,
    DEFAULT_DELETE_DEVICES_ON_SYNC,
    APPLY_IMPORT_TAG,
)
from nautobot_ssot_aristacv.diffsync import cvutils


name = "SSoT - Arista CloudVision"  # pylint: disable=invalid-name


class CloudVisionDataSource(DataSource, Job):
    """CloudVision SSoT Data Source."""

    debug = BooleanVar(description="Enable for more verbose debug logging")

    class Meta:
        """Meta data for DataSource."""

        name = "CloudVision ⟹ Nautobot"
        data_source = "Cloudvision"
        data_source_icon = static("nautobot_ssot_aristacv/cvp_logo.png")
        description = "Sync system tag data from CloudVision to Nautobot"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataSource."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_aristacv", {})
        if configs.get("cvp_host"):
            return {
                "Server type": "On prem",
                "CloudVision host": configs.get("cvp_host"),
                "Username": configs.get("cvp_user"),
                "Insecure": configs.get("insecure"),
                "Delete devices on sync": configs.get("delete_devices_on_sync", str(DEFAULT_DELETE_DEVICES_ON_SYNC)),
                "New device default site": configs.get("from_cloudvision_default_site", DEFAULT_SITE),
                "New device default role": configs.get("from_cloudvision_default_device_role", DEFAULT_DEVICE_ROLE),
                "New device default role color": configs.get(
                    "from_cloudvision_default_device_role_color", DEFAULT_DEVICE_ROLE_COLOR
                ),
                "New device default status": configs.get(
                    "from_cloudvision_default_device_status", DEFAULT_DEVICE_STATUS
                ),
                "New device default status color": configs.get(
                    "from_cloudvision_default_device_status_color", DEFAULT_DEVICE_STATUS_COLOR
                ),
                "Apply import tag": str(configs.get("apply_import_tag", APPLY_IMPORT_TAG))
                # Password is intentionally omitted!
            }
        return {
            "Server type": "CVaaS",
            "CloudVision host": configs.get("cvaas_url"),
            "Delete devices on sync": configs.get("delete_devices_on_sync", str(DEFAULT_DELETE_DEVICES_ON_SYNC)),
            "New device default site": configs.get("from_cloudvision_default_site", DEFAULT_SITE),
            "New device default role": configs.get("from_cloudvision_default_device_role", DEFAULT_DEVICE_ROLE),
            "New device default role color": configs.get(
                "from_cloudvision_default_device_role_color", DEFAULT_DEVICE_ROLE_COLOR
            ),
            "New device default status": configs.get("from_cloudvision_default_device_status", DEFAULT_DEVICE_STATUS),
            "New device default status color": configs.get(
                "from_cloudvision_default_device_status_color", DEFAULT_DEVICE_STATUS_COLOR
            ),
            "Apply import tag": str(configs.get("apply_import_tag", APPLY_IMPORT_TAG))
            # Token is intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataSource."""
        return (
            DataMapping("topology_network_type", None, "Topology Network Type", None),
            DataMapping("mlag", None, "MLAG", None),
            DataMapping("mpls", None, "mpls", None),
            DataMapping("model", None, "Platform", reverse("dcim:platform_list")),
            DataMapping("systype", None, "systype", None),
            DataMapping("serialnumber", None, "Device Serial Number", None),
            DataMapping("pimbidir", None, "pimbidir", None),
            DataMapping("sflow", None, "sFlow", None),
            DataMapping("eostrain", None, "eostrain", None),
            DataMapping("tapagg", None, "tapagg", None),
            DataMapping("pim", None, "pim", None),
            DataMapping("bgp", None, "bgp", None),
            DataMapping("terminattr", None, "TerminAttr Version", None),
            DataMapping("ztp", None, "ztp", None),
            DataMapping("eos", None, "EOS Version", None),
            DataMapping("topology_type", None, "Topology Type", None),
        )

    def sync_data(self):
        """Sync system tags from CloudVision to Nautobot custom fields."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_aristacv", {})
        if configs.get("delete_devices_on_sync"):
            self.log_warning(
                message="Devices not present in Cloudvision but present in Nautobot will be deleted from Nautobot."
            )
        else:
            self.log_warning(
                message="Devices not present in Cloudvision but present in Nautobot will not be deleted from Nautobot."
            )
        self.log("Connecting to CloudVision")
        cvutils.connect()
        self.log("Loading data from CloudVision")
        cv = C(job=self)
        cv.load()
        self.log("Loading data from Nautobot")
        nb = N(job=self)
        nb.load()
        self.log("Performing diff between Cloudvision and Nautobot.")
        diff = nb.diff_from(cv)
        self.sync.diff = diff.dict()
        self.sync.save()
        self.log(diff.summary())
        if not self.kwargs["dry_run"]:
            self.log("Syncing to Nautbot")
            try:
                nb.sync_from(cv)
            except RpcError as e:
                self.log_failure("Sync failed.")
                raise e
            self.log_success(message="Sync complete.")
        cvutils.disconnect()

    def lookup_object(self, model_name, unique_id):
        """Lookup object for SSoT plugin integration."""
        if model_name == "cf":
            try:
                cf_name, _ = unique_id.split("__")
                return CustomField.objects.get(name=f"{cf_name}")
            except CustomField.DoesNotExist:
                pass
        return None


class CloudVisionDataTarget(DataTarget, Job):
    """CloudVision SSoT Data Target."""

    debug = BooleanVar(description="Enable for more verbose debug logging")

    class Meta:
        """Meta data for DataTarget."""

        name = "Nautobot ⟹ CloudVision"
        data_target = "CloudVision"
        data_target_icon = static("nautobot_ssot_aristacv/cvp_logo.png")
        description = "Sync tag data from Nautobot to CloudVision"

    @classmethod
    def config_information(cls):
        """Dictionary describing the configuration of this DataTarget."""
        configs = settings.PLUGINS_CONFIG.get("nautobot_ssot_aristacv", {})
        if configs.get("cvp_host"):
            return {
                "Server type": "On prem",
                "CloudVision host": configs.get("cvp_host"),
                "Username": configs.get("cvp_user"),
                "Insecure": configs.get("insecure")
                # Password is intentionally omitted!
            }
        return {
            "Server type": "CVaaS",
            "CloudVision host": "www.arista.io",
            # Token is intentionally omitted!
        }

    @classmethod
    def data_mappings(cls):
        """List describing the data mappings involved in this DataTarget."""
        return (DataMapping("Tags", reverse("extras:tag_list"), "Device Tags", None),)

    def sync_data(self):
        """Sync device tags from CloudVision to Nautobot."""
        self.log("Connecting to CloudVision")
        cvutils.connect()
        self.log("Loading data from CloudVision")
        cv = CloudVision(job=self)
        cv.load()
        self.log("Loading data from Nautobot")
        nb = Nautobot()
        nb.load()
        self.log("Performing diff between Nautobot and Cloudvision")
        diff = cv.diff_from(nb)
        self.sync.diff = diff.dict()
        self.sync.save()
        self.log(diff.summary())
        # if self.kwargs["debug"]:
        #     self.log_debug(diff_nb_cv.dict())
        if not self.kwargs["dry_run"]:
            self.log("Syncing to CloudVision")
            try:
                nb.sync_to(cv)
            except RpcError as e:
                self.log_failure("Sync failed.")
                raise e
            self.log_success(message="Sync complete")
        cvutils.disconnect()

    def lookup_object(self, model_name, unique_id):
        """Lookup object for SSoT plugin integration."""
        if model_name == "tag":
            try:
                tag_name, value = unique_id.split("__")
                return Tag.objects.get(name=f"{tag_name}:{value}")
            except Tag.DoesNotExist:
                pass
        return None


jobs = [CloudVisionDataSource, CloudVisionDataTarget]
