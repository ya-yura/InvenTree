"""JSON API for the Stock app."""

from collections import OrderedDict
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import F, Q
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.utils.translation import gettext_lazy as _

from django_filters import rest_framework as rest_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.response import Response
from rest_framework.serializers import ValidationError

import common.models
import common.settings
import stock.serializers as StockSerializers
from build.models import Build
from company.models import Company, SupplierPart
from company.serializers import CompanySerializer, SupplierPartSerializer
from InvenTree.api import (APIDownloadMixin, AttachmentMixin,
                           ListCreateDestroyAPIView, MetadataView, StatusView)
from InvenTree.filters import InvenTreeOrderingFilter
from InvenTree.helpers import (DownloadFile, extract_serial_numbers, isNull,
                               str2bool, str2int)
from InvenTree.mixins import (CreateAPI, CustomRetrieveUpdateDestroyAPI,
                              ListAPI, ListCreateAPI, RetrieveAPI,
                              RetrieveUpdateDestroyAPI)
from InvenTree.status_codes import StockHistoryCode, StockStatus
from order.models import (PurchaseOrder, ReturnOrder, SalesOrder,
                          SalesOrderAllocation)
from order.serializers import (PurchaseOrderSerializer, ReturnOrderSerializer,
                               SalesOrderSerializer)
from part.models import BomItem, Part, PartCategory
from part.serializers import PartBriefSerializer
from stock.admin import LocationResource, StockItemResource
from stock.models import (StockItem, StockItemAttachment, StockItemTestResult,
                          StockItemTracking, StockLocation)


class StockDetail(RetrieveUpdateDestroyAPI):
    """API detail endpoint for Stock object.

    get:
    Return a single StockItem object

    post:
    Update a StockItem

    delete:
    Remove a StockItem
    """

    queryset = StockItem.objects.all()
    serializer_class = StockSerializers.StockItemSerializer

    def get_queryset(self, *args, **kwargs):
        """Annotate queryset."""
        queryset = super().get_queryset(*args, **kwargs)
        queryset = StockSerializers.StockItemSerializer.annotate_queryset(queryset)

        return queryset

    def get_serializer_context(self):
        """Extend serializer context."""
        ctx = super().get_serializer_context()
        ctx['user'] = getattr(self.request, 'user', None)

        return ctx

    def get_serializer(self, *args, **kwargs):
        """Set context before returning serializer."""
        kwargs['part_detail'] = True
        kwargs['location_detail'] = True
        kwargs['supplier_part_detail'] = True
        kwargs['context'] = self.get_serializer_context()

        return self.serializer_class(*args, **kwargs)


class StockItemContextMixin:
    """Mixin class for adding StockItem object to serializer context."""

    queryset = StockItem.objects.none()

    def get_serializer_context(self):
        """Extend serializer context."""
        context = super().get_serializer_context()
        context['request'] = self.request

        try:
            context['item'] = StockItem.objects.get(pk=self.kwargs.get('pk', None))
        except Exception:
            pass

        return context


class StockItemSerialize(StockItemContextMixin, CreateAPI):
    """API endpoint for serializing a stock item."""

    serializer_class = StockSerializers.SerializeStockItemSerializer


class StockItemInstall(StockItemContextMixin, CreateAPI):
    """API endpoint for installing a particular stock item into this stock item.

    - stock_item.part must be in the BOM for this part
    - stock_item must currently be "in stock"
    - stock_item must be serialized (and not belong to another item)
    """

    serializer_class = StockSerializers.InstallStockItemSerializer


class StockItemUninstall(StockItemContextMixin, CreateAPI):
    """API endpoint for removing (uninstalling) items from this item."""

    serializer_class = StockSerializers.UninstallStockItemSerializer


class StockItemConvert(StockItemContextMixin, CreateAPI):
    """API endpoint for converting a stock item to a variant part"""

    serializer_class = StockSerializers.ConvertStockItemSerializer


class StockItemReturn(StockItemContextMixin, CreateAPI):
    """API endpoint for returning a stock item from a customer"""

    serializer_class = StockSerializers.ReturnStockItemSerializer


class StockAdjustView(CreateAPI):
    """A generic class for handling stocktake actions.

    Subclasses exist for:

    - StockCount: count stock items
    - StockAdd: add stock items
    - StockRemove: remove stock items
    - StockTransfer: transfer stock items
    """

    queryset = StockItem.objects.none()

    def get_serializer_context(self):
        """Extend serializer context."""
        context = super().get_serializer_context()
        context['request'] = self.request

        return context


class StockCount(StockAdjustView):
    """Endpoint for counting stock (performing a stocktake)."""

    serializer_class = StockSerializers.StockCountSerializer


class StockAdd(StockAdjustView):
    """Endpoint for adding a quantity of stock to an existing StockItem."""

    serializer_class = StockSerializers.StockAddSerializer


class StockRemove(StockAdjustView):
    """Endpoint for removing a quantity of stock from an existing StockItem."""

    serializer_class = StockSerializers.StockRemoveSerializer


class StockTransfer(StockAdjustView):
    """API endpoint for performing stock movements."""

    serializer_class = StockSerializers.StockTransferSerializer


class StockAssign(CreateAPI):
    """API endpoint for assigning stock to a particular customer."""

    queryset = StockItem.objects.all()
    serializer_class = StockSerializers.StockAssignmentSerializer

    def get_serializer_context(self):
        """Extend serializer context."""
        ctx = super().get_serializer_context()
        ctx['request'] = self.request

        return ctx


class StockMerge(CreateAPI):
    """API endpoint for merging multiple stock items."""

    queryset = StockItem.objects.none()
    serializer_class = StockSerializers.StockMergeSerializer

    def get_serializer_context(self):
        """Extend serializer context."""
        ctx = super().get_serializer_context()
        ctx['request'] = self.request
        return ctx


class StockLocationList(APIDownloadMixin, ListCreateAPI):
    """API endpoint for list view of StockLocation objects.

    - GET: Return list of StockLocation objects
    - POST: Create a new StockLocation
    """

    queryset = StockLocation.objects.all()
    serializer_class = StockSerializers.LocationSerializer

    def download_queryset(self, queryset, export_format):
        """Download the filtered queryset as a data file"""

        dataset = LocationResource().export(queryset=queryset)
        filedata = dataset.export(export_format)
        filename = f"InvenTree_Locations.{export_format}"

        return DownloadFile(filedata, filename)

    def get_queryset(self, *args, **kwargs):
        """Return annotated queryset for the StockLocationList endpoint"""

        queryset = super().get_queryset(*args, **kwargs)
        queryset = StockSerializers.LocationSerializer.annotate_queryset(queryset)
        return queryset

    def filter_queryset(self, queryset):
        """Custom filtering: - Allow filtering by "null" parent to retrieve top-level stock locations."""
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        loc_id = params.get('parent', None)

        cascade = str2bool(params.get('cascade', False))

        depth = str2int(params.get('depth', None))

        # Do not filter by location
        if loc_id is None:
            pass
        # Look for top-level locations
        elif isNull(loc_id):

            # If we allow "cascade" at the top-level, this essentially means *all* locations
            if not cascade:
                queryset = queryset.filter(parent=None)

            if cascade and depth is not None:
                queryset = queryset.filter(level__lte=depth)

        else:

            try:
                location = StockLocation.objects.get(pk=loc_id)

                # All sub-locations to be returned too?
                if cascade:
                    parents = location.get_descendants(include_self=True)
                    if depth is not None:
                        parents = parents.filter(level__lte=location.level + depth)

                    parent_ids = [p.id for p in parents]
                    queryset = queryset.filter(parent__in=parent_ids)

                else:
                    queryset = queryset.filter(parent=location)

            except (ValueError, StockLocation.DoesNotExist):
                pass

        # Exclude StockLocation tree
        exclude_tree = params.get('exclude_tree', None)

        if exclude_tree is not None:
            try:
                loc = StockLocation.objects.get(pk=exclude_tree)

                queryset = queryset.exclude(
                    pk__in=[subloc.pk for subloc in loc.get_descendants(include_self=True)]
                )

            except (ValueError, StockLocation.DoesNotExist):
                pass

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        'name',
        'structural',
        'external',
    ]

    search_fields = [
        'name',
        'description',
    ]

    ordering_fields = [
        'name',
        'pathstring',
        'items',
        'level',
        'tree_id',
        'lft',
    ]

    ordering = [
        'tree_id',
        'lft',
        'name',
    ]


class StockLocationTree(ListAPI):
    """API endpoint for accessing a list of StockLocation objects, ready for rendering as a tree."""

    queryset = StockLocation.objects.all()
    serializer_class = StockSerializers.LocationTreeSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]

    # Order by tree level (top levels first) and then name
    ordering = ['level', 'name']


class StockFilter(rest_filters.FilterSet):
    """FilterSet for StockItem LIST API."""

    class Meta:
        """Metaclass options for this filterset"""

        model = StockItem

        # Simple filter filters
        fields = [
            'supplier_part',
            'belongs_to',
            'build',
            'customer',
            'sales_order',
            'purchase_order',
        ]

    # Relationship filters
    manufactuer = rest_filters.ModelChoiceFilter(label='Manufacturer', queryset=Company.objects.filter(is_manufacturer=True), field_name='manufacturer_part__manufacturer')
    supplier = rest_filters.ModelChoiceFilter(label='Supplier', queryset=Company.objects.filter(is_supplier=True), field_name='supplier_part__supplier')

    # Part name filters
    name = rest_filters.CharFilter(label='Part name (case insensitive)', field_name='part__name', lookup_expr='iexact')
    name_contains = rest_filters.CharFilter(label='Part name contains (case insensitive)', field_name='part__name', lookup_expr='icontains')
    name_regex = rest_filters.CharFilter(label='Part name (regex)', field_name='part__name', lookup_expr='iregex')

    # Part IPN filters
    IPN = rest_filters.CharFilter(label='Part IPN (case insensitive)', field_name='part__IPN', lookup_expr='iexact')
    IPN_contains = rest_filters.CharFilter(label='Part IPN contains (case insensitive)', field_name='part__IPN', lookup_expr='icontains')
    IPN_regex = rest_filters.CharFilter(label='Part IPN (regex)', field_name='part__IPN', lookup_expr='iregex')

    # Part attribute filters
    assembly = rest_filters.BooleanFilter(label="Assembly", field_name='part__assembly')
    active = rest_filters.BooleanFilter(label="Active", field_name='part__active')

    min_stock = rest_filters.NumberFilter(label='Minimum stock', field_name='quantity', lookup_expr='gte')
    max_stock = rest_filters.NumberFilter(label='Maximum stock', field_name='quantity', lookup_expr='lte')

    status = rest_filters.NumberFilter(label='Status Code', method='filter_status')

    def filter_status(self, queryset, name, value):
        """Filter by integer status code"""

        return queryset.filter(status=value)

    allocated = rest_filters.BooleanFilter(label='Is Allocated', method='filter_allocated')

    def filter_allocated(self, queryset, name, value):
        """Filter by whether or not the stock item is 'allocated'"""

        if str2bool(value):
            # Filter StockItem with either build allocations or sales order allocations
            return queryset.filter(Q(sales_order_allocations__isnull=False) | Q(allocations__isnull=False))
        else:
            # Filter StockItem without build allocations or sales order allocations
            return queryset.filter(Q(sales_order_allocations__isnull=True) & Q(allocations__isnull=True))

    expired = rest_filters.BooleanFilter(label='Expired', method='filter_expired')

    def filter_expired(self, queryset, name, value):
        """Filter by whether or not the stock item has expired"""

        if not common.settings.stock_expiry_enabled():
            return queryset

        if str2bool(value):
            return queryset.filter(StockItem.EXPIRED_FILTER)
        else:
            return queryset.exclude(StockItem.EXPIRED_FILTER)

    external = rest_filters.BooleanFilter(label=_('External Location'), method='filter_external')

    def filter_external(self, queryset, name, value):
        """Filter by whether or not the stock item is located in an external location"""

        if str2bool(value):
            return queryset.filter(location__external=True)
        else:
            return queryset.exclude(location__external=True)

    in_stock = rest_filters.BooleanFilter(label='In Stock', method='filter_in_stock')

    def filter_in_stock(self, queryset, name, value):
        """Filter by if item is in stock."""
        if str2bool(value):
            return queryset.filter(StockItem.IN_STOCK_FILTER)
        else:
            return queryset.exclude(StockItem.IN_STOCK_FILTER)

    available = rest_filters.BooleanFilter(label='Available', method='filter_available')

    def filter_available(self, queryset, name, value):
        """Filter by whether the StockItem is "available" or not.

        Here, "available" means that the allocated quantity is less than the total quantity
        """
        if str2bool(value):
            # The 'quantity' field is greater than the calculated 'allocated' field
            return queryset.filter(Q(quantity__gt=F('allocated')))
        else:
            # The 'quantity' field is less than (or equal to) the calculated 'allocated' field
            return queryset.filter(Q(quantity__lte=F('allocated')))

    batch = rest_filters.CharFilter(label="Batch code filter (case insensitive)", lookup_expr='iexact')

    batch_regex = rest_filters.CharFilter(label="Batch code filter (regex)", field_name='batch', lookup_expr='iregex')

    is_building = rest_filters.BooleanFilter(label="In production")

    # Serial number filtering
    serial_gte = rest_filters.NumberFilter(label='Serial number GTE', field_name='serial', lookup_expr='gte')
    serial_lte = rest_filters.NumberFilter(label='Serial number LTE', field_name='serial', lookup_expr='lte')
    serial = rest_filters.CharFilter(label='Serial number', field_name='serial', lookup_expr='exact')

    serialized = rest_filters.BooleanFilter(label='Has serial number', method='filter_serialized')

    def filter_serialized(self, queryset, name, value):
        """Filter by whether the StockItem has a serial number (or not)."""
        q = Q(serial=None) | Q(serial='')

        if str2bool(value):
            return queryset.exclude(q)
        else:
            return queryset.filter(q)

    has_batch = rest_filters.BooleanFilter(label='Has batch code', method='filter_has_batch')

    def filter_has_batch(self, queryset, name, value):
        """Filter by whether the StockItem has a batch code (or not)."""
        q = Q(batch=None) | Q(batch='')

        if str2bool(value):
            return queryset.exclude(q)
        else:
            return queryset.filter(q)

    tracked = rest_filters.BooleanFilter(label='Tracked', method='filter_tracked')

    def filter_tracked(self, queryset, name, value):
        """Filter by whether this stock item is *tracked*.

        Meaning either:
        - It has a serial number
        - It has a batch code
        """
        q_batch = Q(batch=None) | Q(batch='')
        q_serial = Q(serial=None) | Q(serial='')

        if str2bool(value):
            return queryset.exclude(q_batch & q_serial)
        else:
            return queryset.filter(q_batch & q_serial)

    installed = rest_filters.BooleanFilter(label='Installed in other stock item', method='filter_installed')

    def filter_installed(self, queryset, name, value):
        """Filter stock items by "belongs_to" field being empty."""
        if str2bool(value):
            return queryset.exclude(belongs_to=None)
        else:
            return queryset.filter(belongs_to=None)

    sent_to_customer = rest_filters.BooleanFilter(label='Sent to customer', method='filter_sent_to_customer')

    def filter_sent_to_customer(self, queryset, name, value):
        """Filter by sent to customer."""
        if str2bool(value):
            return queryset.exclude(customer=None)
        else:
            return queryset.filter(customer=None)

    depleted = rest_filters.BooleanFilter(label='Depleted', method='filter_depleted')

    def filter_depleted(self, queryset, name, value):
        """Filter by depleted items."""
        if str2bool(value):
            return queryset.filter(quantity__lte=0)
        else:
            return queryset.exclude(quantity__lte=0)

    has_purchase_price = rest_filters.BooleanFilter(label='Has purchase price', method='filter_has_purchase_price')

    def filter_has_purchase_price(self, queryset, name, value):
        """Filter by having a purchase price."""
        if str2bool(value):
            return queryset.exclude(purchase_price=None)
        else:
            return queryset.filter(purchase_price=None)

    # Update date filters
    updated_before = rest_filters.DateFilter(label='Updated before', field_name='updated', lookup_expr='lte')
    updated_after = rest_filters.DateFilter(label='Updated after', field_name='updated', lookup_expr='gte')


class StockList(APIDownloadMixin, ListCreateDestroyAPIView):
    """API endpoint for list view of Stock objects.

    - GET: Return a list of all StockItem objects (with optional query filters)
    - POST: Create a new StockItem
    """

    serializer_class = StockSerializers.StockItemSerializer
    queryset = StockItem.objects.all()
    filterset_class = StockFilter

    def get_serializer_context(self):
        """Extend serializer context."""
        ctx = super().get_serializer_context()
        ctx['user'] = getattr(self.request, 'user', None)

        return ctx

    def create(self, request, *args, **kwargs):
        """Create a new StockItem object via the API.

        We override the default 'create' implementation.

        If a location is *not* specified, but the linked *part* has a default location,
        we can pre-fill the location automatically.
        """
        user = request.user

        # Copy the request data, to side-step "mutability" issues
        data = OrderedDict()
        # Update with cleaned input data
        data.update(self.clean_data(request.data))

        quantity = data.get('quantity', None)

        if quantity is None:
            raise ValidationError({
                'quantity': _('Quantity is required'),
            })

        try:
            part = Part.objects.get(pk=data.get('part', None))
        except (ValueError, Part.DoesNotExist):
            raise ValidationError({
                'part': _('Valid part must be supplied'),
            })

        # Set default location (if not provided)
        if 'location' not in data:
            location = part.get_default_location()

            if location:
                data['location'] = location.pk

        # An expiry date was *not* specified - try to infer it!
        if 'expiry_date' not in data and part.default_expiry > 0:
            data['expiry_date'] = datetime.now().date() + timedelta(days=part.default_expiry)

        # Attempt to extract serial numbers from submitted data
        serials = None

        # Check if a set of serial numbers was provided
        serial_numbers = data.get('serial_numbers', '')

        # Assign serial numbers for a trackable part
        if serial_numbers:

            if not part.trackable:
                raise ValidationError({
                    'serial_numbers': [_("Serial numbers cannot be supplied for a non-trackable part")]
                })

            # If serial numbers are specified, check that they match!
            try:
                serials = extract_serial_numbers(
                    serial_numbers,
                    quantity,
                    part.get_latest_serial_number()
                )

                # Determine if any of the specified serial numbers are invalid
                # Note "invalid" means either they already exist, or do not pass custom rules
                invalid = []
                errors = []

                for serial in serials:
                    try:
                        part.validate_serial_number(serial, raise_error=True)
                    except DjangoValidationError as exc:
                        # Catch raised error to extract specific error information
                        invalid.append(serial)

                        if exc.message not in errors:
                            errors.append(exc.message)

                if len(errors) > 0:

                    msg = _("The following serial numbers already exist or are invalid")
                    msg += " : "
                    msg += ",".join([str(e) for e in invalid])

                    raise ValidationError({
                        'serial_numbers': errors + [msg]
                    })

            except DjangoValidationError as e:
                raise ValidationError({
                    'quantity': e.messages,
                    'serial_numbers': e.messages,
                })

        if serials is not None:
            """If the stock item is going to be serialized, set the quantity to 1."""
            data['quantity'] = 1

        # De-serialize the provided data
        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():

            # Create an initial StockItem object
            item = serializer.save()

            if serials:
                # Assign the first serial number to the "master" item
                item.serial = serials[0]

            # Save the item (with user information)
            item.save(user=user)

            if serials:
                for serial in serials[1:]:

                    # Create a duplicate stock item with the next serial number
                    item.pk = None
                    item.serial = serial

                    item.save(user=user)

                response_data = {
                    'quantity': quantity,
                    'serial_numbers': serials,
                }

            else:
                response_data = serializer.data

            return Response(response_data, status=status.HTTP_201_CREATED, headers=self.get_success_headers(serializer.data))

    def download_queryset(self, queryset, export_format):
        """Download this queryset as a file.

        Uses the APIDownloadMixin mixin class
        """
        dataset = StockItemResource().export(queryset=queryset)

        filedata = dataset.export(export_format)

        filename = 'InvenTree_StockItems_{date}.{fmt}'.format(
            date=datetime.now().strftime("%d-%b-%Y"),
            fmt=export_format
        )

        return DownloadFile(filedata, filename)

    def list(self, request, *args, **kwargs):
        """Override the 'list' method, as the StockLocation objects are very expensive to serialize.

        So, we fetch and serialize the required StockLocation objects only as required.
        """
        queryset = self.filter_queryset(self.get_queryset())

        params = request.query_params

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        # Keep track of which related models we need to query
        location_ids = set()
        part_ids = set()
        supplier_part_ids = set()

        # Iterate through each StockItem and grab some data
        for item in data:
            loc = item['location']
            if loc:
                location_ids.add(loc)

            part = item['part']
            if part:
                part_ids.add(part)

            sp = item['supplier_part']

            if sp:
                supplier_part_ids.add(sp)

        # Do we wish to include Part detail?
        if str2bool(params.get('part_detail', False)):

            # Fetch only the required Part objects from the database
            parts = Part.objects.filter(pk__in=part_ids).prefetch_related(
                'category',
            )

            part_map = {}

            for part in parts:
                part_map[part.pk] = PartBriefSerializer(part).data

            # Now update each StockItem with the related Part data
            for stock_item in data:
                part_id = stock_item['part']
                stock_item['part_detail'] = part_map.get(part_id, None)

        # Do we wish to include SupplierPart detail?
        if str2bool(params.get('supplier_part_detail', False)):

            supplier_parts = SupplierPart.objects.filter(pk__in=supplier_part_ids)

            supplier_part_map = {}

            for part in supplier_parts:
                supplier_part_map[part.pk] = SupplierPartSerializer(part).data

            for stock_item in data:
                part_id = stock_item['supplier_part']
                stock_item['supplier_part_detail'] = supplier_part_map.get(part_id, None)

        # Do we wish to include StockLocation detail?
        if str2bool(params.get('location_detail', False)):

            # Fetch only the required StockLocation objects from the database
            locations = StockLocation.objects.filter(pk__in=location_ids).prefetch_related(
                'parent',
                'children',
            )

            location_map = {}

            # Serialize each StockLocation object
            for location in locations:
                location_map[location.pk] = StockSerializers.LocationBriefSerializer(location).data

            # Now update each StockItem with the related StockLocation data
            for stock_item in data:
                loc_id = stock_item['location']
                stock_item['location_detail'] = location_map.get(loc_id, None)

        """
        Determine the response type based on the request.
        a) For HTTP requests (e.g. via the browseable API) return a DRF response
        b) For AJAX requests, simply return a JSON rendered response.

        Note: b) is about 100x quicker than a), because the DRF framework adds a lot of cruft
        """

        if page is not None:
            return self.get_paginated_response(data)
        elif request.is_ajax():
            return JsonResponse(data, safe=False)
        else:
            return Response(data)

    def get_queryset(self, *args, **kwargs):
        """Annotate queryset before returning."""
        queryset = super().get_queryset(*args, **kwargs)

        queryset = StockSerializers.StockItemSerializer.annotate_queryset(queryset)

        # Also ensure that we pre-fecth all the related items
        queryset = queryset.prefetch_related(
            'part',
            'part__category',
            'location'
        )

        return queryset

    def filter_queryset(self, queryset):
        """Custom filtering for the StockItem queryset."""
        params = self.request.query_params

        queryset = super().filter_queryset(queryset)

        if common.settings.stock_expiry_enabled():

            # Filter by 'expiry date'
            expired_date_lte = params.get('expiry_date_lte', None)
            if expired_date_lte is not None:
                try:
                    date_lte = datetime.fromisoformat(expired_date_lte)
                    queryset = queryset.filter(expiry_date__lte=date_lte)
                except (ValueError, TypeError):
                    pass

            expiry_date_gte = params.get('expiry_date_gte', None)
            if expiry_date_gte is not None:
                try:
                    date_gte = datetime.fromisoformat(expiry_date_gte)
                    queryset = queryset.filter(expiry_date__gte=date_gte)
                except (ValueError, TypeError):
                    pass

            # Filter by 'stale' status
            stale = params.get('stale', None)

            if stale is not None:
                stale = str2bool(stale)

                # How many days to account for "staleness"?
                stale_days = common.models.InvenTreeSetting.get_setting('STOCK_STALE_DAYS')

                if stale_days > 0:
                    stale_date = datetime.now().date() + timedelta(days=stale_days)

                    stale_filter = StockItem.IN_STOCK_FILTER & ~Q(expiry_date=None) & Q(expiry_date__lt=stale_date)

                    if stale:
                        queryset = queryset.filter(stale_filter)
                    else:
                        queryset = queryset.exclude(stale_filter)

        # Exclude stock item tree
        exclude_tree = params.get('exclude_tree', None)

        if exclude_tree is not None:
            try:
                item = StockItem.objects.get(pk=exclude_tree)

                queryset = queryset.exclude(
                    pk__in=[it.pk for it in item.get_descendants(include_self=True)]
                )

            except (ValueError, StockItem.DoesNotExist):
                pass

        # Filter by "part tree" - only allow parts within a given variant tree
        part_tree = params.get('part_tree', None)

        if part_tree is not None:
            try:
                part = Part.objects.get(pk=part_tree)

                if part.tree_id is not None:
                    queryset = queryset.filter(part__tree_id=part.tree_id)
            except Exception:
                pass

        # Exclude StockItems which are already allocated to a particular SalesOrder
        exclude_so_allocation = params.get('exclude_so_allocation', None)

        if exclude_so_allocation is not None:

            try:
                order = SalesOrder.objects.get(pk=exclude_so_allocation)

                # Grab all the active SalesOrderAllocations for this order
                allocations = SalesOrderAllocation.objects.filter(
                    line__pk__in=[
                        line.pk for line in order.lines.all()
                    ]
                )

                # Exclude any stock item which is already allocated to the sales order
                queryset = queryset.exclude(
                    pk__in=[
                        a.item.pk for a in allocations
                    ]
                )

            except (ValueError, SalesOrder.DoesNotExist):
                pass

        # Does the client wish to filter by the Part ID?
        part_id = params.get('part', None)

        if part_id:
            try:
                part = Part.objects.get(pk=part_id)

                # Do we wish to filter *just* for this part, or also for parts *under* this one?
                include_variants = str2bool(params.get('include_variants', True))

                if include_variants:
                    # Filter by any parts "under" the given part
                    parts = part.get_descendants(include_self=True)

                    queryset = queryset.filter(part__in=parts)

                else:
                    queryset = queryset.filter(part=part)

            except (ValueError, Part.DoesNotExist):
                raise ValidationError({"part": "Invalid Part ID specified"})

        # Does the client wish to filter by the 'ancestor'?
        anc_id = params.get('ancestor', None)

        if anc_id:
            try:
                ancestor = StockItem.objects.get(pk=anc_id)

                # Only allow items which are descendants of the specified StockItem
                queryset = queryset.filter(id__in=[item.pk for item in ancestor.children.all()])

            except (ValueError, Part.DoesNotExist):
                raise ValidationError({"ancestor": "Invalid ancestor ID specified"})

        # Does the client wish to filter by stock location?
        loc_id = params.get('location', None)

        cascade = str2bool(params.get('cascade', True))

        if loc_id is not None:

            # Filter by 'null' location (i.e. top-level items)
            if isNull(loc_id):
                if not cascade:
                    queryset = queryset.filter(location=None)
            else:
                try:
                    # If '?cascade=true' then include items which exist in sub-locations
                    if cascade:
                        location = StockLocation.objects.get(pk=loc_id)
                        queryset = queryset.filter(location__in=location.getUniqueChildren())
                    else:
                        queryset = queryset.filter(location=loc_id)

                except (ValueError, StockLocation.DoesNotExist):
                    pass

        # Does the client wish to filter by part category?
        cat_id = params.get('category', None)

        if cat_id:
            try:
                category = PartCategory.objects.get(pk=cat_id)
                queryset = queryset.filter(part__category__in=category.getUniqueChildren())

            except (ValueError, PartCategory.DoesNotExist):
                raise ValidationError({"category": "Invalid category id specified"})

        # Does the client wish to filter by BomItem
        bom_item_id = params.get('bom_item', None)

        if bom_item_id is not None:
            try:
                bom_item = BomItem.objects.get(pk=bom_item_id)

                queryset = queryset.filter(bom_item.get_stock_filter())

            except (ValueError, BomItem.DoesNotExist):
                pass

        # Filter by company (either manufacturer or supplier)
        company = params.get('company', None)

        if company is not None:
            queryset = queryset.filter(Q(supplier_part__supplier=company) | Q(supplier_part__manufacturer_part__manufacturer=company))

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        InvenTreeOrderingFilter,
    ]

    ordering_field_aliases = {
        'SKU': 'supplier_part__SKU',
        'stock': ['quantity', 'serial_int', 'serial'],
    }

    ordering_fields = [
        'batch',
        'location',
        'part__name',
        'part__IPN',
        'updated',
        'stocktake_date',
        'expiry_date',
        'quantity',
        'stock',
        'status',
        'SKU',
    ]

    ordering = [
        'part__name',
        'quantity',
        'location',
    ]

    search_fields = [
        'serial',
        'batch',
        'part__name',
        'part__IPN',
        'part__description',
        'location__name',
    ]


class StockAttachmentList(AttachmentMixin, ListCreateDestroyAPIView):
    """API endpoint for listing (and creating) a StockItemAttachment (file upload)."""

    queryset = StockItemAttachment.objects.all()
    serializer_class = StockSerializers.StockItemAttachmentSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]

    filterset_fields = [
        'stock_item',
    ]


class StockAttachmentDetail(AttachmentMixin, RetrieveUpdateDestroyAPI):
    """Detail endpoint for StockItemAttachment."""

    queryset = StockItemAttachment.objects.all()
    serializer_class = StockSerializers.StockItemAttachmentSerializer


class StockItemTestResultDetail(RetrieveUpdateDestroyAPI):
    """Detail endpoint for StockItemTestResult."""

    queryset = StockItemTestResult.objects.all()
    serializer_class = StockSerializers.StockItemTestResultSerializer


class StockItemTestResultList(ListCreateDestroyAPIView):
    """API endpoint for listing (and creating) a StockItemTestResult object."""

    queryset = StockItemTestResult.objects.all()
    serializer_class = StockSerializers.StockItemTestResultSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        'test',
        'user',
        'result',
        'value',
    ]

    ordering = 'date'

    def filter_queryset(self, queryset):
        """Filter by build or stock_item."""
        params = self.request.query_params

        queryset = super().filter_queryset(queryset)

        # Filter by 'build'
        build = params.get('build', None)

        if build is not None:

            try:
                build = Build.objects.get(pk=build)

                queryset = queryset.filter(stock_item__build=build)

            except (ValueError, Build.DoesNotExist):
                pass

        # Filter by stock item
        item = params.get('stock_item', None)

        if item is not None:
            try:
                item = StockItem.objects.get(pk=item)

                items = [item]

                # Do we wish to also include test results for 'installed' items?
                include_installed = str2bool(params.get('include_installed', False))

                if include_installed:
                    # Include items which are installed "underneath" this item
                    # Note that this function is recursive!
                    installed_items = item.get_installed_items(cascade=True)

                    items += [it for it in installed_items]

                queryset = queryset.filter(stock_item__in=items)

            except (ValueError, StockItem.DoesNotExist):
                pass

        return queryset

    def get_serializer(self, *args, **kwargs):
        """Set context before returning serializer."""
        try:
            kwargs['user_detail'] = str2bool(self.request.query_params.get('user_detail', False))
        except Exception:
            pass

        kwargs['context'] = self.get_serializer_context()

        return self.serializer_class(*args, **kwargs)

    def perform_create(self, serializer):
        """Create a new test result object.

        Also, check if an attachment was uploaded alongside the test result,
        and save it to the database if it were.
        """
        # Capture the user information
        test_result = serializer.save()
        test_result.user = self.request.user
        test_result.save()


class StockTrackingDetail(RetrieveAPI):
    """Detail API endpoint for StockItemTracking model."""

    queryset = StockItemTracking.objects.all()
    serializer_class = StockSerializers.StockTrackingSerializer


class StockTrackingList(ListAPI):
    """API endpoint for list view of StockItemTracking objects.

    StockItemTracking objects are read-only
    (they are created by internal model functionality)

    - GET: Return list of StockItemTracking objects
    """

    queryset = StockItemTracking.objects.all()
    serializer_class = StockSerializers.StockTrackingSerializer

    def get_serializer(self, *args, **kwargs):
        """Set context before returning serializer."""
        try:
            kwargs['item_detail'] = str2bool(self.request.query_params.get('item_detail', False))
        except Exception:
            pass

        try:
            kwargs['user_detail'] = str2bool(self.request.query_params.get('user_detail', False))
        except Exception:
            pass

        kwargs['context'] = self.get_serializer_context()

        return self.serializer_class(*args, **kwargs)

    def list(self, request, *args, **kwargs):
        """List all stock tracking entries."""
        queryset = self.filter_queryset(self.get_queryset())

        serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        # Attempt to add extra context information to the historical data
        for item in data:
            deltas = item['deltas']

            if not deltas:
                deltas = {}

            # Add part detail
            if 'part' in deltas:
                try:
                    part = Part.objects.get(pk=deltas['part'])
                    serializer = PartBriefSerializer(part)
                    deltas['part_detail'] = serializer.data
                except Exception:
                    pass

            # Add location detail
            if 'location' in deltas:
                try:
                    location = StockLocation.objects.get(pk=deltas['location'])
                    serializer = StockSerializers.LocationSerializer(location)
                    deltas['location_detail'] = serializer.data
                except Exception:
                    pass

            # Add stockitem detail
            if 'stockitem' in deltas:
                try:
                    stockitem = StockItem.objects.get(pk=deltas['stockitem'])
                    serializer = StockSerializers.StockItemSerializer(stockitem)
                    deltas['stockitem_detail'] = serializer.data
                except Exception:
                    pass

            # Add customer detail
            if 'customer' in deltas:
                try:
                    customer = Company.objects.get(pk=deltas['customer'])
                    serializer = CompanySerializer(customer)
                    deltas['customer_detail'] = serializer.data
                except Exception:
                    pass

            # Add PurchaseOrder detail
            if 'purchaseorder' in deltas:
                try:
                    order = PurchaseOrder.objects.get(pk=deltas['purchaseorder'])
                    serializer = PurchaseOrderSerializer(order)
                    deltas['purchaseorder_detail'] = serializer.data
                except Exception:
                    pass

            # Add SalesOrder detail
            if 'salesorder' in deltas:
                try:
                    order = SalesOrder.objects.get(pk=deltas['salesorder'])
                    serializer = SalesOrderSerializer(order)
                    deltas['salesorder_detail'] = serializer.data
                except Exception:
                    pass

            # Add ReturnOrder detail
            if 'returnorder' in deltas:
                try:
                    order = ReturnOrder.objects.get(pk=deltas['returnorder'])
                    serializer = ReturnOrderSerializer(order)
                    deltas['returnorder_detail'] = serializer.data
                except Exception:
                    pass

        if request.is_ajax():
            return JsonResponse(data, safe=False)
        else:
            return Response(data)

    def create(self, request, *args, **kwargs):
        """Create a new StockItemTracking object.

        Here we override the default 'create' implementation,
        to save the user information associated with the request object.
        """
        # Clean up input data
        data = self.clean_data(request.data)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)

        # Record the user who created this Part object
        item = serializer.save()
        item.user = request.user
        item.system = False

        # quantity field cannot be explicitly adjusted  here
        item.quantity = item.item.quantity
        item.save()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        'item',
        'user',
    ]

    ordering = '-date'

    ordering_fields = [
        'date',
    ]

    search_fields = [
        'title',
        'notes',
    ]


class LocationDetail(CustomRetrieveUpdateDestroyAPI):
    """API endpoint for detail view of StockLocation object.

    - GET: Return a single StockLocation object
    - PATCH: Update a StockLocation object
    - DELETE: Remove a StockLocation object
    """

    queryset = StockLocation.objects.all()
    serializer_class = StockSerializers.LocationSerializer

    def get_queryset(self, *args, **kwargs):
        """Return annotated queryset for the StockLocationList endpoint"""

        queryset = super().get_queryset(*args, **kwargs)
        queryset = StockSerializers.LocationSerializer.annotate_queryset(queryset)
        return queryset

    def destroy(self, request, *args, **kwargs):
        """Delete a Stock location instance via the API"""
        delete_stock_items = 'delete_stock_items' in request.data and request.data['delete_stock_items'] == '1'
        delete_sub_locations = 'delete_sub_locations' in request.data and request.data['delete_sub_locations'] == '1'
        return super().destroy(request,
                               *args,
                               **dict(kwargs,
                                      delete_sub_locations=delete_sub_locations,
                                      delete_stock_items=delete_stock_items))


stock_api_urls = [
    re_path(r'^location/', include([

        re_path(r'^tree/', StockLocationTree.as_view(), name='api-location-tree'),

        # Stock location detail endpoints
        path(r'<int:pk>/', include([

            re_path(r'^metadata/', MetadataView.as_view(), {'model': StockLocation}, name='api-location-metadata'),

            re_path(r'^.*$', LocationDetail.as_view(), name='api-location-detail'),
        ])),

        re_path(r'^.*$', StockLocationList.as_view(), name='api-location-list'),
    ])),

    # Endpoints for bulk stock adjustment actions
    re_path(r'^count/', StockCount.as_view(), name='api-stock-count'),
    re_path(r'^add/', StockAdd.as_view(), name='api-stock-add'),
    re_path(r'^remove/', StockRemove.as_view(), name='api-stock-remove'),
    re_path(r'^transfer/', StockTransfer.as_view(), name='api-stock-transfer'),
    re_path(r'^assign/', StockAssign.as_view(), name='api-stock-assign'),
    re_path(r'^merge/', StockMerge.as_view(), name='api-stock-merge'),

    # StockItemAttachment API endpoints
    re_path(r'^attachment/', include([
        path(r'<int:pk>/', StockAttachmentDetail.as_view(), name='api-stock-attachment-detail'),
        path('', StockAttachmentList.as_view(), name='api-stock-attachment-list'),
    ])),

    # StockItemTestResult API endpoints
    re_path(r'^test/', include([
        path(r'<int:pk>/', StockItemTestResultDetail.as_view(), name='api-stock-test-result-detail'),
        re_path(r'^.*$', StockItemTestResultList.as_view(), name='api-stock-test-result-list'),
    ])),

    # StockItemTracking API endpoints
    re_path(r'^track/', include([
        path(r'<int:pk>/', StockTrackingDetail.as_view(), name='api-stock-tracking-detail'),

        # Stock tracking status code information
        re_path(r'status/', StatusView.as_view(), {StatusView.MODEL_REF: StockHistoryCode}, name='api-stock-tracking-status-codes'),

        re_path(r'^.*$', StockTrackingList.as_view(), name='api-stock-tracking-list'),
    ])),

    # Detail views for a single stock item
    path(r'<int:pk>/', include([
        re_path(r'^convert/', StockItemConvert.as_view(), name='api-stock-item-convert'),
        re_path(r'^install/', StockItemInstall.as_view(), name='api-stock-item-install'),
        re_path(r'^metadata/', MetadataView.as_view(), {'model': StockItem}, name='api-stock-item-metadata'),
        re_path(r'^return/', StockItemReturn.as_view(), name='api-stock-item-return'),
        re_path(r'^serialize/', StockItemSerialize.as_view(), name='api-stock-item-serialize'),
        re_path(r'^uninstall/', StockItemUninstall.as_view(), name='api-stock-item-uninstall'),
        re_path(r'^.*$', StockDetail.as_view(), name='api-stock-detail'),
    ])),

    # Stock item status code information
    re_path(r'status/', StatusView.as_view(), {StatusView.MODEL_REF: StockStatus}, name='api-stock-status-codes'),

    # Anything else
    re_path(r'^.*$', StockList.as_view(), name='api-stock-list'),
]
