"""Provides a JSON API for the Part app."""

import functools

from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.urls import include, path, re_path
from django.utils.translation import gettext_lazy as _

from django_filters import rest_framework as rest_filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

import order.models
from build.models import Build, BuildItem
from InvenTree.api import (APIDownloadMixin, AttachmentMixin,
                           ListCreateDestroyAPIView, MetadataView)
from InvenTree.filters import InvenTreeOrderingFilter
from InvenTree.helpers import (DownloadFile, increment_serial_number, isNull,
                               str2bool, str2int)
from InvenTree.mixins import (CreateAPI, CustomRetrieveUpdateDestroyAPI,
                              ListAPI, ListCreateAPI, RetrieveAPI,
                              RetrieveUpdateAPI, RetrieveUpdateDestroyAPI,
                              UpdateAPI)
from InvenTree.permissions import RolePermission
from InvenTree.status_codes import (BuildStatus, PurchaseOrderStatus,
                                    SalesOrderStatus)
from part.admin import PartCategoryResource, PartResource

from . import serializers as part_serializers
from . import views
from .models import (BomItem, BomItemSubstitute, Part, PartAttachment,
                     PartCategory, PartCategoryParameterTemplate,
                     PartInternalPriceBreak, PartParameter,
                     PartParameterTemplate, PartRelated, PartSellPriceBreak,
                     PartStocktake, PartStocktakeReport, PartTestTemplate)


class CategoryMixin:
    """Mixin class for PartCategory endpoints"""
    serializer_class = part_serializers.CategorySerializer
    queryset = PartCategory.objects.all()

    def get_queryset(self, *args, **kwargs):
        """Return an annotated queryset for the CategoryDetail endpoint"""

        queryset = super().get_queryset(*args, **kwargs)
        queryset = part_serializers.CategorySerializer.annotate_queryset(queryset)
        return queryset

    def get_serializer_context(self):
        """Add extra context to the serializer for the CategoryDetail endpoint"""
        ctx = super().get_serializer_context()

        try:
            ctx['starred_categories'] = [star.category for star in self.request.user.starred_categories.all()]
        except AttributeError:
            # Error is thrown if the view does not have an associated request
            ctx['starred_categories'] = []

        return ctx


class CategoryList(CategoryMixin, APIDownloadMixin, ListCreateAPI):
    """API endpoint for accessing a list of PartCategory objects.

    - GET: Return a list of PartCategory objects
    - POST: Create a new PartCategory object
    """

    def download_queryset(self, queryset, export_format):
        """Download the filtered queryset as a data file"""

        dataset = PartCategoryResource().export(queryset=queryset)
        filedata = dataset.export(export_format)
        filename = f"InvenTree_Categories.{export_format}"

        return DownloadFile(filedata, filename)

    def filter_queryset(self, queryset):
        """Custom filtering:

        - Allow filtering by "null" parent to retrieve top-level part categories
        """
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        cat_id = params.get('parent', None)

        cascade = str2bool(params.get('cascade', False))

        depth = str2int(params.get('depth', None))

        # Do not filter by category
        if cat_id is None:
            pass
        # Look for top-level categories
        elif isNull(cat_id):

            if not cascade:
                queryset = queryset.filter(parent=None)

            if cascade and depth is not None:
                queryset = queryset.filter(level__lte=depth)

        else:
            try:
                category = PartCategory.objects.get(pk=cat_id)

                if cascade:
                    parents = category.get_descendants(include_self=True)
                    if depth is not None:
                        parents = parents.filter(level__lte=category.level + depth)

                    parent_ids = [p.id for p in parents]

                    queryset = queryset.filter(parent__in=parent_ids)
                else:
                    queryset = queryset.filter(parent=category)

            except (ValueError, PartCategory.DoesNotExist):
                pass

        # Exclude PartCategory tree
        exclude_tree = params.get('exclude_tree', None)

        if exclude_tree is not None:
            try:
                cat = PartCategory.objects.get(pk=exclude_tree)

                queryset = queryset.exclude(
                    pk__in=[c.pk for c in cat.get_descendants(include_self=True)]
                )

            except (ValueError, PartCategory.DoesNotExist):
                pass

        # Filter by "starred" status
        starred = params.get('starred', None)

        if starred is not None:
            starred = str2bool(starred)
            starred_categories = [star.category.pk for star in self.request.user.starred_categories.all()]

            if starred:
                queryset = queryset.filter(pk__in=starred_categories)
            else:
                queryset = queryset.exclude(pk__in=starred_categories)

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        'name',
        'description',
        'structural'
    ]

    ordering_fields = [
        'name',
        'pathstring',
        'level',
        'tree_id',
        'lft',
        'part_count',
    ]

    # Use hierarchical ordering by default
    ordering = [
        'tree_id',
        'lft',
        'name'
    ]

    search_fields = [
        'name',
        'description',
    ]


class CategoryDetail(CategoryMixin, CustomRetrieveUpdateDestroyAPI):
    """API endpoint for detail view of a single PartCategory object."""

    def update(self, request, *args, **kwargs):
        """Perform 'update' function and mark this part as 'starred' (or not)"""
        # Clean up input data
        data = self.clean_data(request.data)

        if 'starred' in data:
            starred = str2bool(data.get('starred', False))

            self.get_object().set_starred(request.user, starred)

        response = super().update(request, *args, **kwargs)

        return response

    def destroy(self, request, *args, **kwargs):
        """Delete a Part category instance via the API"""
        delete_parts = 'delete_parts' in request.data and request.data['delete_parts'] == '1'
        delete_child_categories = 'delete_child_categories' in request.data and request.data['delete_child_categories'] == '1'
        return super().destroy(request,
                               *args,
                               **dict(kwargs,
                                      delete_parts=delete_parts,
                                      delete_child_categories=delete_child_categories))


class CategoryTree(ListAPI):
    """API endpoint for accessing a list of PartCategory objects ready for rendering a tree."""

    queryset = PartCategory.objects.all()
    serializer_class = part_serializers.CategoryTree

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]

    # Order by tree level (top levels first) and then name
    ordering = ['level', 'name']


class CategoryParameterList(ListCreateAPI):
    """API endpoint for accessing a list of PartCategoryParameterTemplate objects.

    - GET: Return a list of PartCategoryParameterTemplate objects
    """

    queryset = PartCategoryParameterTemplate.objects.all()
    serializer_class = part_serializers.CategoryParameterTemplateSerializer

    def get_queryset(self):
        """Custom filtering:

        - Allow filtering by "null" parent to retrieve all categories parameter templates
        - Allow filtering by category
        - Allow traversing all parent categories
        """
        queryset = super().get_queryset()

        params = self.request.query_params

        category = params.get('category', None)

        if category is not None:
            try:

                category = PartCategory.objects.get(pk=category)

                fetch_parent = str2bool(params.get('fetch_parent', True))

                if fetch_parent:
                    parents = category.get_ancestors(include_self=True)
                    queryset = queryset.filter(category__in=[cat.pk for cat in parents])
                else:
                    queryset = queryset.filter(category=category)

            except (ValueError, PartCategory.DoesNotExist):
                pass

        return queryset


class CategoryParameterDetail(RetrieveUpdateDestroyAPI):
    """Detail endpoint fro the PartCategoryParameterTemplate model"""

    queryset = PartCategoryParameterTemplate.objects.all()
    serializer_class = part_serializers.CategoryParameterTemplateSerializer


class PartSalePriceDetail(RetrieveUpdateDestroyAPI):
    """Detail endpoint for PartSellPriceBreak model."""

    queryset = PartSellPriceBreak.objects.all()
    serializer_class = part_serializers.PartSalePriceSerializer


class PartSalePriceList(ListCreateAPI):
    """API endpoint for list view of PartSalePriceBreak model."""

    queryset = PartSellPriceBreak.objects.all()
    serializer_class = part_serializers.PartSalePriceSerializer

    filter_backends = [
        DjangoFilterBackend
    ]

    filterset_fields = [
        'part',
    ]


class PartInternalPriceDetail(RetrieveUpdateDestroyAPI):
    """Detail endpoint for PartInternalPriceBreak model."""

    queryset = PartInternalPriceBreak.objects.all()
    serializer_class = part_serializers.PartInternalPriceSerializer


class PartInternalPriceList(ListCreateAPI):
    """API endpoint for list view of PartInternalPriceBreak model."""

    queryset = PartInternalPriceBreak.objects.all()
    serializer_class = part_serializers.PartInternalPriceSerializer
    permission_required = 'roles.sales_order.show'

    filter_backends = [
        DjangoFilterBackend
    ]

    filterset_fields = [
        'part',
    ]


class PartAttachmentList(AttachmentMixin, ListCreateDestroyAPIView):
    """API endpoint for listing (and creating) a PartAttachment (file upload)."""

    queryset = PartAttachment.objects.all()
    serializer_class = part_serializers.PartAttachmentSerializer

    filter_backends = [
        DjangoFilterBackend,
    ]

    filterset_fields = [
        'part',
    ]


class PartAttachmentDetail(AttachmentMixin, RetrieveUpdateDestroyAPI):
    """Detail endpoint for PartAttachment model."""

    queryset = PartAttachment.objects.all()
    serializer_class = part_serializers.PartAttachmentSerializer


class PartTestTemplateDetail(RetrieveUpdateDestroyAPI):
    """Detail endpoint for PartTestTemplate model."""

    queryset = PartTestTemplate.objects.all()
    serializer_class = part_serializers.PartTestTemplateSerializer


class PartTestTemplateList(ListCreateAPI):
    """API endpoint for listing (and creating) a PartTestTemplate."""

    queryset = PartTestTemplate.objects.all()
    serializer_class = part_serializers.PartTestTemplateSerializer

    def filter_queryset(self, queryset):
        """Filter the test list queryset.

        If filtering by 'part', we include results for any parts "above" the specified part.
        """
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        part = params.get('part', None)

        # Filter by part
        if part:
            try:
                part = Part.objects.get(pk=part)
                queryset = queryset.filter(part__in=part.get_ancestors(include_self=True))
            except (ValueError, Part.DoesNotExist):
                pass

        # Filter by 'required' status
        required = params.get('required', None)

        if required is not None:
            queryset = queryset.filter(required=str2bool(required))

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]


class PartThumbs(ListAPI):
    """API endpoint for retrieving information on available Part thumbnails."""

    queryset = Part.objects.all()
    serializer_class = part_serializers.PartThumbSerializer

    def get_queryset(self):
        """Return a queryset which exlcudes any parts without images"""
        queryset = super().get_queryset()

        # Get all Parts which have an associated image
        queryset = queryset.exclude(image='')

        return queryset

    def list(self, request, *args, **kwargs):
        """Serialize the available Part images.

        - Images may be used for multiple parts!
        """
        queryset = self.filter_queryset(self.get_queryset())

        # Return the most popular parts first
        data = queryset.values(
            'image',
        ).annotate(count=Count('image')).order_by('-count')

        return Response(data)

    filter_backends = [
        filters.SearchFilter,
    ]

    search_fields = [
        'name',
        'description',
        'IPN',
        'revision',
        'keywords',
        'category__name',
    ]


class PartThumbsUpdate(RetrieveUpdateAPI):
    """API endpoint for updating Part thumbnails."""

    queryset = Part.objects.all()
    serializer_class = part_serializers.PartThumbSerializerUpdate

    filter_backends = [
        DjangoFilterBackend
    ]


class PartScheduling(RetrieveAPI):
    """API endpoint for delivering "scheduling" information about a given part via the API.

    Returns a chronologically ordered list about future "scheduled" events,
    concerning stock levels for the part:

    - Purchase Orders (incoming stock)
    - Sales Orders (outgoing stock)
    - Build Orders (incoming completed stock)
    - Build Orders (outgoing allocated stock)
    """

    queryset = Part.objects.all()

    def retrieve(self, request, *args, **kwargs):
        """Return scheduling information for the referenced Part instance"""

        part = self.get_object()

        schedule = []

        def add_schedule_entry(date, quantity, title, label, url, speculative_quantity=0):
            """Check if a scheduled entry should be added:

            - date must be non-null
            - date cannot be in the "past"
            - quantity must not be zero
            """

            schedule.append({
                'date': date,
                'quantity': quantity,
                'speculative_quantity': speculative_quantity,
                'title': title,
                'label': label,
                'url': url,
            })

        # Add purchase order (incoming stock) information
        po_lines = order.models.PurchaseOrderLineItem.objects.filter(
            part__part=part,
            order__status__in=PurchaseOrderStatus.OPEN,
        )

        for line in po_lines:

            target_date = line.target_date or line.order.target_date

            quantity = max(line.quantity - line.received, 0)

            # Multiply by the pack_size of the SupplierPart
            quantity *= line.part.pack_size

            add_schedule_entry(
                target_date,
                quantity,
                _('Incoming Purchase Order'),
                str(line.order),
                line.order.get_absolute_url()
            )

        # Add sales order (outgoing stock) information
        so_lines = order.models.SalesOrderLineItem.objects.filter(
            part=part,
            order__status__in=SalesOrderStatus.OPEN,
        )

        for line in so_lines:

            target_date = line.target_date or line.order.target_date

            quantity = max(line.quantity - line.shipped, 0)

            add_schedule_entry(
                target_date,
                -quantity,
                _('Outgoing Sales Order'),
                str(line.order),
                line.order.get_absolute_url(),
            )

        # Add build orders (incoming stock) information
        build_orders = Build.objects.filter(
            part=part,
            status__in=BuildStatus.ACTIVE_CODES
        )

        for build in build_orders:

            quantity = max(build.quantity - build.completed, 0)

            add_schedule_entry(
                build.target_date,
                quantity,
                _('Stock produced by Build Order'),
                str(build),
                build.get_absolute_url(),
            )

        """
        Add build order allocation (outgoing stock) information.

        Here we need some careful consideration:

        - 'Tracked' stock items are removed from stock when the individual Build Output is completed
        - 'Untracked' stock items are removed from stock when the Build Order is completed

        The 'simplest' approach here is to look at existing BuildItem allocations which reference this part,
        and "schedule" them for removal at the time of build order completion.

        This assumes that the user is responsible for correctly allocating parts.

        However, it has the added benefit of side-stepping the various BOM substition options,
        and just looking at what stock items the user has actually allocated against the Build.
        """

        # Grab a list of BomItem objects that this part might be used in
        bom_items = BomItem.objects.filter(part.get_used_in_bom_item_filter())

        # Track all outstanding build orders
        seen_builds = set()

        for bom_item in bom_items:
            # Find a list of active builds for this BomItem

            if bom_item.inherited:
                # An "inherited" BOM item filters down to variant parts also
                childs = bom_item.part.get_descendants(include_self=True)
                builds = Build.objects.filter(
                    status__in=BuildStatus.ACTIVE_CODES,
                    part__in=childs,
                )
            else:
                builds = Build.objects.filter(
                    status__in=BuildStatus.ACTIVE_CODES,
                    part=bom_item.part,
                )

            for build in builds:

                # Ensure we don't double-count any builds
                if build in seen_builds:
                    continue

                seen_builds.add(build)

                if bom_item.sub_part.trackable:
                    # Trackable parts are allocated against the outputs
                    required_quantity = build.remaining * bom_item.quantity
                else:
                    # Non-trackable parts are allocated against the build itself
                    required_quantity = build.quantity * bom_item.quantity

                # Grab all allocations against the spefied BomItem
                allocations = BuildItem.objects.filter(
                    bom_item=bom_item,
                    build=build,
                )

                # Total allocated for *this* part
                part_allocated_quantity = 0

                # Total allocated for *any* part
                total_allocated_quantity = 0

                for allocation in allocations:
                    total_allocated_quantity += allocation.quantity

                    if allocation.stock_item.part == part:
                        part_allocated_quantity += allocation.quantity

                speculative_quantity = 0

                # Consider the case where the build order is *not* fully allocated
                if required_quantity > total_allocated_quantity:
                    speculative_quantity = -1 * (required_quantity - total_allocated_quantity)

                add_schedule_entry(
                    build.target_date,
                    -part_allocated_quantity,
                    _('Stock required for Build Order'),
                    str(build),
                    build.get_absolute_url(),
                    speculative_quantity=speculative_quantity
                )

        def compare(entry_1, entry_2):
            """Comparison function for sorting entries by date.

            Account for the fact that either date might be None
            """

            date_1 = entry_1['date']
            date_2 = entry_2['date']

            if date_1 is None:
                return -1
            elif date_2 is None:
                return 1

            return -1 if date_1 < date_2 else 1

        # Sort by incrementing date values
        schedule = sorted(schedule, key=functools.cmp_to_key(compare))

        return Response(schedule)


class PartRequirements(RetrieveAPI):
    """API endpoint detailing 'requirements' information for a particular part.

    This endpoint returns information on upcoming requirements for:

    - Sales Orders
    - Build Orders
    - Total requirements

    As this data is somewhat complex to calculate, is it not included in the default API
    """

    queryset = Part.objects.all()

    def retrieve(self, request, *args, **kwargs):
        """Construct a response detailing Part requirements"""

        part = self.get_object()

        data = {
            "available_stock": part.available_stock,
            "on_order": part.on_order,
            "required_build_order_quantity": part.required_build_order_quantity(),
            "allocated_build_order_quantity": part.build_order_allocation_count(),
            "required_sales_order_quantity": part.required_sales_order_quantity(),
            "allocated_sales_order_quantity": part.sales_order_allocation_count(pending=True),
        }

        data["allocated"] = data["allocated_build_order_quantity"] + data["allocated_sales_order_quantity"]
        data["required"] = data["required_build_order_quantity"] + data["required_sales_order_quantity"]

        return Response(data)


class PartPricingDetail(RetrieveUpdateAPI):
    """API endpoint for viewing part pricing data"""

    serializer_class = part_serializers.PartPricingSerializer
    queryset = Part.objects.all()

    def get_object(self):
        """Return the PartPricing object associated with the linked Part"""

        part = super().get_object()
        return part.pricing

    def _get_serializer(self, *args, **kwargs):
        """Return a part pricing serializer object"""

        part = self.get_object()
        kwargs['instance'] = part.pricing

        return self.serializer_class(**kwargs)


class PartSerialNumberDetail(RetrieveAPI):
    """API endpoint for returning extra serial number information about a particular part."""

    queryset = Part.objects.all()

    def retrieve(self, request, *args, **kwargs):
        """Return serial number information for the referenced Part instance"""
        part = self.get_object()

        # Calculate the "latest" serial number
        latest = part.get_latest_serial_number()

        data = {
            'latest': latest,
        }

        if latest is not None:
            next_serial = increment_serial_number(latest)

            if next_serial != latest:
                data['next'] = next_serial

        return Response(data)


class PartCopyBOM(CreateAPI):
    """API endpoint for duplicating a BOM."""

    queryset = Part.objects.all()
    serializer_class = part_serializers.PartCopyBOMSerializer

    def get_serializer_context(self):
        """Add custom information to the serializer context for this endpoint"""
        ctx = super().get_serializer_context()

        try:
            ctx['part'] = Part.objects.get(pk=self.kwargs.get('pk', None))
        except Exception:
            pass

        return ctx


class PartValidateBOM(RetrieveUpdateAPI):
    """API endpoint for 'validating' the BOM for a given Part."""

    class BOMValidateSerializer(serializers.ModelSerializer):
        """Simple serializer class for validating a single BomItem instance"""

        class Meta:
            """Metaclass defines serializer fields"""
            model = Part
            fields = [
                'checksum',
                'valid',
            ]

        checksum = serializers.CharField(
            read_only=True,
            source='bom_checksum',
        )

        valid = serializers.BooleanField(
            write_only=True,
            default=False,
            label=_('Valid'),
            help_text=_('Validate entire Bill of Materials'),
        )

        def validate_valid(self, valid):
            """Check that the 'valid' input was flagged"""
            if not valid:
                raise ValidationError(_('This option must be selected'))

    queryset = Part.objects.all()

    serializer_class = BOMValidateSerializer

    def update(self, request, *args, **kwargs):
        """Validate the referenced BomItem instance"""
        part = self.get_object()

        partial = kwargs.pop('partial', False)

        # Clean up input data before using it
        data = self.clean_data(request.data)

        serializer = self.get_serializer(part, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)

        part.validate_bom(request.user)

        return Response({
            'checksum': part.bom_checksum,
        })


class PartFilter(rest_filters.FilterSet):
    """Custom filters for the PartList endpoint.

    Uses the django_filters extension framework
    """

    # Filter by parts which have (or not) an IPN value
    has_ipn = rest_filters.BooleanFilter(label='Has IPN', method='filter_has_ipn')

    def filter_has_ipn(self, queryset, name, value):
        """Filter by whether the Part has an IPN (internal part number) or not"""
        value = str2bool(value)

        if value:
            queryset = queryset.exclude(IPN='')
        else:
            queryset = queryset.filter(IPN='')

        return queryset

    # Regex filter for name
    name_regex = rest_filters.CharFilter(label='Filter by name (regex)', field_name='name', lookup_expr='iregex')

    # Exact match for IPN
    IPN = rest_filters.CharFilter(
        label='Filter by exact IPN (internal part number)',
        field_name='IPN',
        lookup_expr="iexact"
    )

    # Regex match for IPN
    IPN_regex = rest_filters.CharFilter(label='Filter by regex on IPN (internal part number)', field_name='IPN', lookup_expr='iregex')

    # low_stock filter
    low_stock = rest_filters.BooleanFilter(label='Low stock', method='filter_low_stock')

    def filter_low_stock(self, queryset, name, value):
        """Filter by "low stock" status."""
        value = str2bool(value)

        if value:
            # Ignore any parts which do not have a specified 'minimum_stock' level
            queryset = queryset.exclude(minimum_stock=0)
            # Filter items which have an 'in_stock' level lower than 'minimum_stock'
            queryset = queryset.filter(Q(in_stock__lt=F('minimum_stock')))
        else:
            # Filter items which have an 'in_stock' level higher than 'minimum_stock'
            queryset = queryset.filter(Q(in_stock__gte=F('minimum_stock')))

        return queryset

    # has_stock filter
    has_stock = rest_filters.BooleanFilter(label='Has stock', method='filter_has_stock')

    def filter_has_stock(self, queryset, name, value):
        """Filter by whether the Part has any stock"""
        value = str2bool(value)

        if value:
            queryset = queryset.filter(Q(in_stock__gt=0))
        else:
            queryset = queryset.filter(Q(in_stock__lte=0))

        return queryset

    # unallocated_stock filter
    unallocated_stock = rest_filters.BooleanFilter(label='Unallocated stock', method='filter_unallocated_stock')

    def filter_unallocated_stock(self, queryset, name, value):
        """Filter by whether the Part has unallocated stock"""
        value = str2bool(value)

        if value:
            queryset = queryset.filter(Q(unallocated_stock__gt=0))
        else:
            queryset = queryset.filter(Q(unallocated_stock__lte=0))

        return queryset

    convert_from = rest_filters.ModelChoiceFilter(label="Can convert from", queryset=Part.objects.all(), method='filter_convert_from')

    def filter_convert_from(self, queryset, name, part):
        """Limit the queryset to valid conversion options for the specified part"""
        conversion_options = part.get_conversion_options()

        queryset = queryset.filter(pk__in=conversion_options)

        return queryset

    exclude_tree = rest_filters.ModelChoiceFilter(label="Exclude Part tree", queryset=Part.objects.all(), method='filter_exclude_tree')

    def filter_exclude_tree(self, queryset, name, part):
        """Exclude all parts and variants 'down' from the specified part from the queryset"""

        children = part.get_descendants(include_self=True)

        queryset = queryset.exclude(id__in=children)

        return queryset

    ancestor = rest_filters.ModelChoiceFilter(label='Ancestor', queryset=Part.objects.all(), method='filter_ancestor')

    def filter_ancestor(self, queryset, name, part):
        """Limit queryset to descendants of the specified ancestor part"""

        descendants = part.get_descendants(include_self=False)
        queryset = queryset.filter(id__in=descendants)

        return queryset

    variant_of = rest_filters.ModelChoiceFilter(label='Variant Of', queryset=Part.objects.all(), method='filter_variant_of')

    def filter_variant_of(self, queryset, name, part):
        """Limit queryset to direct children (variants) of the specified part"""

        queryset = queryset.filter(id__in=part.get_children())
        return queryset

    in_bom_for = rest_filters.ModelChoiceFilter(label='In BOM Of', queryset=Part.objects.all(), method='filter_in_bom')

    def filter_in_bom(self, queryset, name, part):
        """Limit queryset to parts in the BOM for the specified part"""

        bom_parts = part.get_parts_in_bom()
        queryset = queryset.filter(id__in=[p.pk for p in bom_parts])
        return queryset

    has_pricing = rest_filters.BooleanFilter(label="Has Pricing", method="filter_has_pricing")

    def filter_has_pricing(self, queryset, name, value):
        """Filter the queryset based on whether pricing information is available for the sub_part"""

        value = str2bool(value)

        q_a = Q(pricing_data=None)
        q_b = Q(pricing_data__overall_min=None, pricing_data__overall_max=None)

        if value:
            queryset = queryset.exclude(q_a | q_b)
        else:
            queryset = queryset.filter(q_a | q_b)

        return queryset

    stocktake = rest_filters.BooleanFilter(label="Has stocktake", method='filter_has_stocktake')

    def filter_has_stocktake(self, queryset, name, value):
        """Filter the queryset based on whether stocktake data is available"""

        value = str2bool(value)

        if (value):
            queryset = queryset.exclude(last_stocktake=None)
        else:
            queryset = queryset.filter(last_stocktake=None)

        return queryset

    is_template = rest_filters.BooleanFilter()

    assembly = rest_filters.BooleanFilter()

    component = rest_filters.BooleanFilter()

    trackable = rest_filters.BooleanFilter()

    purchaseable = rest_filters.BooleanFilter()

    salable = rest_filters.BooleanFilter()

    active = rest_filters.BooleanFilter()

    virtual = rest_filters.BooleanFilter()


class PartMixin:
    """Mixin class for Part API endpoints"""
    serializer_class = part_serializers.PartSerializer
    queryset = Part.objects.all()

    starred_parts = None

    is_create = False

    def get_queryset(self, *args, **kwargs):
        """Return an annotated queryset object for the PartDetail endpoint"""
        queryset = super().get_queryset(*args, **kwargs)

        queryset = part_serializers.PartSerializer.annotate_queryset(queryset)

        return queryset

    def get_serializer(self, *args, **kwargs):
        """Return a serializer instance for this endpoint"""
        # Ensure the request context is passed through
        kwargs['context'] = self.get_serializer_context()

        # Indicate that we can create a new Part via this endpoint
        kwargs['create'] = self.is_create

        # Pass a list of "starred" parts to the current user to the serializer
        # We do this to reduce the number of database queries required!
        if self.starred_parts is None and self.request is not None:
            self.starred_parts = [star.part for star in self.request.user.starred_parts.all()]

        kwargs['starred_parts'] = self.starred_parts

        try:
            params = self.request.query_params

            kwargs['parameters'] = str2bool(params.get('parameters', None))
            kwargs['category_detail'] = str2bool(params.get('category_detail', False))

        except AttributeError:
            pass

        return self.serializer_class(*args, **kwargs)

    def get_serializer_context(self):
        """Extend serializer context data"""
        context = super().get_serializer_context()
        context['request'] = self.request

        return context


class PartList(PartMixin, APIDownloadMixin, ListCreateAPI):
    """API endpoint for accessing a list of Part objects, or creating a new Part instance"""

    filterset_class = PartFilter
    is_create = True

    def download_queryset(self, queryset, export_format):
        """Download the filtered queryset as a data file"""
        dataset = PartResource().export(queryset=queryset)

        filedata = dataset.export(export_format)
        filename = f"InvenTree_Parts.{export_format}"

        return DownloadFile(filedata, filename)

    def list(self, request, *args, **kwargs):
        """Overide the 'list' method, as the PartCategory objects are very expensive to serialize!

        So we will serialize them first, and keep them in memory, so that they do not have to be serialized multiple times...
        """
        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        """
        Determine the response type based on the request.
        a) For HTTP requests (e.g. via the browseable API) return a DRF response
        b) For AJAX requests, simply return a JSON rendered response.
        """
        if page is not None:
            return self.get_paginated_response(data)
        elif request.is_ajax():
            return JsonResponse(data, safe=False)
        else:
            return Response(data)

    def filter_queryset(self, queryset):
        """Perform custom filtering of the queryset"""
        params = self.request.query_params

        queryset = super().filter_queryset(queryset)

        # Exclude specific part ID values?
        exclude_id = []

        for key in ['exclude_id', 'exclude_id[]']:
            if key in params:
                exclude_id += params.getlist(key, [])

        if exclude_id:

            id_values = []

            for val in exclude_id:
                try:
                    # pk values must be integer castable
                    val = int(val)
                    id_values.append(val)
                except ValueError:
                    pass

            queryset = queryset.exclude(pk__in=id_values)

        # Filter by whether the BOM has been validated (or not)
        bom_valid = params.get('bom_valid', None)

        # TODO: Querying bom_valid status may be quite expensive
        # TODO: (It needs to be profiled!)
        # TODO: It might be worth caching the bom_valid status to a database column

        if bom_valid is not None:

            bom_valid = str2bool(bom_valid)

            # Limit queryset to active assemblies
            queryset = queryset.filter(active=True, assembly=True)

            pks = []

            for part in queryset:
                if part.is_bom_valid() == bom_valid:
                    pks.append(part.pk)

            queryset = queryset.filter(pk__in=pks)

        # Filter by 'related' parts?
        related = params.get('related', None)
        exclude_related = params.get('exclude_related', None)

        if related is not None or exclude_related is not None:
            try:
                pk = related if related is not None else exclude_related
                pk = int(pk)

                related_part = Part.objects.get(pk=pk)

                part_ids = set()

                # Return any relationship which points to the part in question
                relation_filter = Q(part_1=related_part) | Q(part_2=related_part)

                for relation in PartRelated.objects.filter(relation_filter):

                    if relation.part_1.pk != pk:
                        part_ids.add(relation.part_1.pk)

                    if relation.part_2.pk != pk:
                        part_ids.add(relation.part_2.pk)

                if related is not None:
                    # Only return related results
                    queryset = queryset.filter(pk__in=[pk for pk in part_ids])
                elif exclude_related is not None:
                    # Exclude related results
                    queryset = queryset.exclude(pk__in=[pk for pk in part_ids])

            except (ValueError, Part.DoesNotExist):
                pass

        # Filter by 'starred' parts?
        starred = params.get('starred', None)

        if starred is not None:
            starred = str2bool(starred)
            starred_parts = [star.part.pk for star in self.request.user.starred_parts.all()]

            if starred:
                queryset = queryset.filter(pk__in=starred_parts)
            else:
                queryset = queryset.exclude(pk__in=starred_parts)

        # Cascade? (Default = True)
        cascade = str2bool(params.get('cascade', True))

        # Does the user wish to filter by category?
        cat_id = params.get('category', None)

        if cat_id is not None:
            # Category has been specified!
            if isNull(cat_id):
                # A 'null' category is the top-level category
                if not cascade:
                    # Do not cascade, only list parts in the top-level category
                    queryset = queryset.filter(category=None)

            else:
                try:
                    category = PartCategory.objects.get(pk=cat_id)

                    # If '?cascade=true' then include parts which exist in sub-categories
                    if cascade:
                        queryset = queryset.filter(category__in=category.getUniqueChildren())
                    # Just return parts directly in the requested category
                    else:
                        queryset = queryset.filter(category=cat_id)
                except (ValueError, PartCategory.DoesNotExist):
                    pass

        # Filer by 'depleted_stock' status -> has no stock and stock items
        depleted_stock = params.get('depleted_stock', None)

        if depleted_stock is not None:
            depleted_stock = str2bool(depleted_stock)

            if depleted_stock:
                queryset = queryset.filter(Q(in_stock=0) & ~Q(stock_item_count=0))

        # Filter by "parts which need stock to complete build"
        stock_to_build = params.get('stock_to_build', None)

        # TODO: This is super expensive, database query wise...
        # TODO: Need to figure out a cheaper way of making this filter query

        if stock_to_build is not None:
            # Get active builds
            builds = Build.objects.filter(status__in=BuildStatus.ACTIVE_CODES)
            # Store parts with builds needing stock
            parts_needed_to_complete_builds = []
            # Filter required parts
            for build in builds:
                parts_needed_to_complete_builds += [part.pk for part in build.required_parts_to_complete_build]

            queryset = queryset.filter(pk__in=parts_needed_to_complete_builds)

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        InvenTreeOrderingFilter,
    ]

    ordering_fields = [
        'name',
        'creation_date',
        'IPN',
        'in_stock',
        'total_in_stock',
        'unallocated_stock',
        'category',
        'last_stocktake',
    ]

    # Default ordering
    ordering = 'name'

    search_fields = [
        'name',
        'description',
        'IPN',
        'revision',
        'keywords',
        'category__name',
        'manufacturer_parts__MPN',
        'supplier_parts__SKU',
    ]


class PartDetail(PartMixin, RetrieveUpdateDestroyAPI):
    """API endpoint for detail view of a single Part object."""

    def destroy(self, request, *args, **kwargs):
        """Delete a Part instance via the API

        - If the part is 'active' it cannot be deleted
        - It must first be marked as 'inactive'
        """
        part = Part.objects.get(pk=int(kwargs['pk']))
        # Check if inactive
        if not part.active:
            # Delete
            return super(PartDetail, self).destroy(request, *args, **kwargs)
        else:
            # Return 405 error
            message = 'Part is active: cannot delete'
            return Response(status=status.HTTP_405_METHOD_NOT_ALLOWED, data=message)

    def update(self, request, *args, **kwargs):
        """Custom update functionality for Part instance.

        - If the 'starred' field is provided, update the 'starred' status against current user
        """
        # Clean input data
        data = self.clean_data(request.data)

        if 'starred' in data:
            starred = str2bool(data.get('starred', False))

            self.get_object().set_starred(request.user, starred)

        response = super().update(request, *args, **kwargs)

        return response


class PartRelatedList(ListCreateAPI):
    """API endpoint for accessing a list of PartRelated objects."""

    queryset = PartRelated.objects.all()
    serializer_class = part_serializers.PartRelationSerializer

    def filter_queryset(self, queryset):
        """Custom queryset filtering"""
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        # Add a filter for "part" - we can filter either part_1 or part_2
        part = params.get('part', None)

        if part is not None:
            try:
                part = Part.objects.get(pk=part)

                queryset = queryset.filter(Q(part_1=part) | Q(part_2=part))

            except (ValueError, Part.DoesNotExist):
                pass

        return queryset


class PartRelatedDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for accessing detail view of a PartRelated object."""

    queryset = PartRelated.objects.all()
    serializer_class = part_serializers.PartRelationSerializer


class PartParameterTemplateList(ListCreateAPI):
    """API endpoint for accessing a list of PartParameterTemplate objects.

    - GET: Return list of PartParameterTemplate objects
    - POST: Create a new PartParameterTemplate object
    """

    queryset = PartParameterTemplate.objects.all()
    serializer_class = part_serializers.PartParameterTemplateSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
        filters.SearchFilter,
    ]

    filterset_fields = [
        'name',
    ]

    search_fields = [
        'name',
    ]

    def filter_queryset(self, queryset):
        """Custom filtering for the PartParameterTemplate API."""
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        # Filtering against a "Part" - return only parameter templates which are referenced by a part
        part = params.get('part', None)

        if part is not None:

            try:
                part = Part.objects.get(pk=part)
                parameters = PartParameter.objects.filter(part=part)
                template_ids = parameters.values_list('template').distinct()
                queryset = queryset.filter(pk__in=[el[0] for el in template_ids])
            except (ValueError, Part.DoesNotExist):
                pass

        # Filtering against a "PartCategory" - return only parameter templates which are referenced by parts in this category
        category = params.get('category', None)

        if category is not None:

            try:
                category = PartCategory.objects.get(pk=category)
                cats = category.get_descendants(include_self=True)
                parameters = PartParameter.objects.filter(part__category__in=cats)
                template_ids = parameters.values_list('template').distinct()
                queryset = queryset.filter(pk__in=[el[0] for el in template_ids])
            except (ValueError, PartCategory.DoesNotExist):
                pass

        return queryset


class PartParameterTemplateDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for accessing the detail view for a PartParameterTemplate object"""

    queryset = PartParameterTemplate.objects.all()
    serializer_class = part_serializers.PartParameterTemplateSerializer


class PartParameterList(ListCreateAPI):
    """API endpoint for accessing a list of PartParameter objects.

    - GET: Return list of PartParameter objects
    - POST: Create a new PartParameter object
    """

    queryset = PartParameter.objects.all()
    serializer_class = part_serializers.PartParameterSerializer

    def get_serializer(self, *args, **kwargs):
        """Return the serializer instance for this API endpoint.

        If requested, extra detail fields are annotated to the queryset:
        - template_detail
        """

        try:
            kwargs['template_detail'] = str2bool(self.request.GET.get('template_detail', True))
        except AttributeError:
            pass

        return self.serializer_class(*args, **kwargs)

    filter_backends = [
        DjangoFilterBackend
    ]

    filterset_fields = [
        'part',
        'template',
    ]


class PartParameterDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for detail view of a single PartParameter object."""

    queryset = PartParameter.objects.all()
    serializer_class = part_serializers.PartParameterSerializer


class PartStocktakeFilter(rest_filters.FilterSet):
    """Custom fitler for the PartStocktakeList endpoint"""

    class Meta:
        """Metaclass options"""

        model = PartStocktake
        fields = [
            'part',
            'user',
        ]


class PartStocktakeList(ListCreateAPI):
    """API endpoint for listing part stocktake information"""

    queryset = PartStocktake.objects.all()
    serializer_class = part_serializers.PartStocktakeSerializer
    filterset_class = PartStocktakeFilter

    def get_serializer_context(self):
        """Extend serializer context data"""
        context = super().get_serializer_context()
        context['request'] = self.request

        return context

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]

    ordering_fields = [
        'part',
        'item_count',
        'quantity',
        'date',
        'user',
        'pk',
    ]

    # Reverse date ordering by default
    ordering = '-pk'


class PartStocktakeDetail(RetrieveUpdateDestroyAPI):
    """Detail API endpoint for a single PartStocktake instance.

    Note: Only staff (admin) users can access this endpoint.
    """

    queryset = PartStocktake.objects.all()
    serializer_class = part_serializers.PartStocktakeSerializer


class PartStocktakeReportList(ListAPI):
    """API endpoint for listing part stocktake report information"""

    queryset = PartStocktakeReport.objects.all()
    serializer_class = part_serializers.PartStocktakeReportSerializer

    filter_backends = [
        DjangoFilterBackend,
        filters.OrderingFilter,
    ]

    ordering_fields = [
        'date',
        'pk',
    ]

    # Newest first, by default
    ordering = '-pk'


class PartStocktakeReportGenerate(CreateAPI):
    """API endpoint for manually generating a new PartStocktakeReport"""

    serializer_class = part_serializers.PartStocktakeReportGenerateSerializer

    permission_classes = [
        permissions.IsAuthenticated,
        RolePermission,
    ]

    role_required = 'stocktake'

    def get_serializer_context(self):
        """Extend serializer context data"""
        context = super().get_serializer_context()
        context['request'] = self.request

        return context


class BomFilter(rest_filters.FilterSet):
    """Custom filters for the BOM list."""

    class Meta:
        """Metaclass options"""

        model = BomItem
        fields = [
            'optional',
            'consumable',
            'inherited',
            'allow_variants',
            'validated',
        ]

    # Filters for linked 'part'
    part_active = rest_filters.BooleanFilter(label='Master part is active', field_name='part__active')
    part_trackable = rest_filters.BooleanFilter(label='Master part is trackable', field_name='part__trackable')

    # Filters for linked 'sub_part'
    sub_part_trackable = rest_filters.BooleanFilter(label='Sub part is trackable', field_name='sub_part__trackable')
    sub_part_assembly = rest_filters.BooleanFilter(label='Sub part is an assembly', field_name='sub_part__assembly')

    available_stock = rest_filters.BooleanFilter(label="Has available stock", method="filter_available_stock")

    def filter_available_stock(self, queryset, name, value):
        """Filter the queryset based on whether each line item has any available stock"""

        value = str2bool(value)

        if value:
            queryset = queryset.filter(available_stock__gt=0)
        else:
            queryset = queryset.filter(available_stock=0)

        return queryset

    on_order = rest_filters.BooleanFilter(label="On order", method="filter_on_order")

    def filter_on_order(self, queryset, name, value):
        """Filter the queryset based on whether each line item has any stock on order"""

        value = str2bool(value)

        if value:
            queryset = queryset.filter(on_order__gt=0)
        else:
            queryset = queryset.filter(on_order=0)

        return queryset

    has_pricing = rest_filters.BooleanFilter(label="Has Pricing", method="filter_has_pricing")

    def filter_has_pricing(self, queryset, name, value):
        """Filter the queryset based on whether pricing information is available for the sub_part"""

        value = str2bool(value)

        q_a = Q(sub_part__pricing_data=None)
        q_b = Q(sub_part__pricing_data__overall_min=None, sub_part__pricing_data__overall_max=None)

        if value:
            queryset = queryset.exclude(q_a | q_b)
        else:
            queryset = queryset.filter(q_a | q_b)

        return queryset


class BomMixin:
    """Mixin class for BomItem API endpoints"""

    serializer_class = part_serializers.BomItemSerializer
    queryset = BomItem.objects.all()

    def get_serializer(self, *args, **kwargs):
        """Return the serializer instance for this API endpoint

        If requested, extra detail fields are annotated to the queryset:
        - part_detail
        - sub_part_detail
        """

        # Do we wish to include extra detail?
        try:
            kwargs['part_detail'] = str2bool(self.request.GET.get('part_detail', None))
        except AttributeError:
            pass

        try:
            kwargs['sub_part_detail'] = str2bool(self.request.GET.get('sub_part_detail', None))
        except AttributeError:
            pass

        # Ensure the request context is passed through!
        kwargs['context'] = self.get_serializer_context()

        return self.serializer_class(*args, **kwargs)

    def get_queryset(self, *args, **kwargs):
        """Return the queryset object for this endpoint"""
        queryset = super().get_queryset(*args, **kwargs)

        queryset = self.get_serializer_class().setup_eager_loading(queryset)
        queryset = self.get_serializer_class().annotate_queryset(queryset)

        return queryset


class BomList(BomMixin, ListCreateDestroyAPIView):
    """API endpoint for accessing a list of BomItem objects.

    - GET: Return list of BomItem objects
    - POST: Create a new BomItem object
    """

    filterset_class = BomFilter

    def list(self, request, *args, **kwargs):
        """Return serialized list response for this endpoint"""

        queryset = self.filter_queryset(self.get_queryset())

        page = self.paginate_queryset(queryset)

        if page is not None:
            serializer = self.get_serializer(page, many=True)
        else:
            serializer = self.get_serializer(queryset, many=True)

        data = serializer.data

        """
        Determine the response type based on the request.
        a) For HTTP requests (e.g. via the browseable API) return a DRF response
        b) For AJAX requests, simply return a JSON rendered response.
        """
        if page is not None:
            return self.get_paginated_response(data)
        elif request.is_ajax():
            return JsonResponse(data, safe=False)
        else:
            return Response(data)

    def filter_queryset(self, queryset):
        """Custom query filtering for the BomItem list API"""
        queryset = super().filter_queryset(queryset)

        params = self.request.query_params

        # Filter by part?
        part = params.get('part', None)

        if part is not None:
            """
            If we are filtering by "part", there are two cases to consider:

            a) Bom items which are defined for *this* part
            b) Inherited parts which are defined for a *parent* part

            So we need to construct two queries!
            """

            # First, check that the part is actually valid!
            try:
                part = Part.objects.get(pk=part)

                queryset = queryset.filter(part.get_bom_item_filter())

            except (ValueError, Part.DoesNotExist):
                pass

        """
        Filter by 'uses'?

        Here we pass a part ID and return BOM items for any assemblies which "use" (or "require") that part.

        There are multiple ways that an assembly can "use" a sub-part:

        A) Directly specifying the sub_part in a BomItem field
        B) Specifing a "template" part with inherited=True
        C) Allowing variant parts to be substituted
        D) Allowing direct substitute parts to be specified

        - BOM items which are "inherited" by parts which are variants of the master BomItem
        """
        uses = params.get('uses', None)

        if uses is not None:

            try:
                # Extract the part we are interested in
                uses_part = Part.objects.get(pk=uses)

                queryset = queryset.filter(uses_part.get_used_in_bom_item_filter())

            except (ValueError, Part.DoesNotExist):
                pass

        return queryset

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        InvenTreeOrderingFilter,
    ]

    search_fields = [
        'reference',
        'sub_part__name',
        'sub_part__description',
        'sub_part__IPN',
        'sub_part__revision',
        'sub_part__keywords',
        'sub_part__category__name',
    ]

    ordering_fields = [
        'quantity',
        'sub_part',
        'available_stock',
    ]

    ordering_field_aliases = {
        'sub_part': 'sub_part__name',
    }


class BomDetail(BomMixin, RetrieveUpdateDestroyAPI):
    """API endpoint for detail view of a single BomItem object."""
    pass


class BomImportUpload(CreateAPI):
    """API endpoint for uploading a complete Bill of Materials.

    It is assumed that the BOM has been extracted from a file using the BomExtract endpoint.
    """

    queryset = Part.objects.all()
    serializer_class = part_serializers.BomImportUploadSerializer

    def create(self, request, *args, **kwargs):
        """Custom create function to return the extracted data."""
        # Clean up input data
        data = self.clean_data(request.data)

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        data = serializer.extract_data()

        return Response(data, status=status.HTTP_201_CREATED, headers=headers)


class BomImportExtract(CreateAPI):
    """API endpoint for extracting BOM data from a BOM file."""

    queryset = Part.objects.none()
    serializer_class = part_serializers.BomImportExtractSerializer


class BomImportSubmit(CreateAPI):
    """API endpoint for submitting BOM data from a BOM file."""

    queryset = BomItem.objects.none()
    serializer_class = part_serializers.BomImportSubmitSerializer


class BomItemValidate(UpdateAPI):
    """API endpoint for validating a BomItem."""

    class BomItemValidationSerializer(serializers.Serializer):
        """Simple serializer for passing a single boolean field"""
        valid = serializers.BooleanField(default=False)

    queryset = BomItem.objects.all()
    serializer_class = BomItemValidationSerializer

    def update(self, request, *args, **kwargs):
        """Perform update request."""
        partial = kwargs.pop('partial', False)

        # Clean up input data
        data = self.clean_data(request.data)
        valid = data.get('valid', False)

        instance = self.get_object()

        serializer = self.get_serializer(instance, data=data, partial=partial)
        serializer.is_valid(raise_exception=True)

        if type(instance) == BomItem:
            instance.validate_hash(valid)

        return Response(serializer.data)


class BomItemSubstituteList(ListCreateAPI):
    """API endpoint for accessing a list of BomItemSubstitute objects."""

    serializer_class = part_serializers.BomItemSubstituteSerializer
    queryset = BomItemSubstitute.objects.all()

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]

    filterset_fields = [
        'part',
        'bom_item',
    ]


class BomItemSubstituteDetail(RetrieveUpdateDestroyAPI):
    """API endpoint for detail view of a single BomItemSubstitute object."""

    queryset = BomItemSubstitute.objects.all()
    serializer_class = part_serializers.BomItemSubstituteSerializer


part_api_urls = [

    # Base URL for PartCategory API endpoints
    re_path(r'^category/', include([
        re_path(r'^tree/', CategoryTree.as_view(), name='api-part-category-tree'),

        re_path(r'^parameters/', include([
            re_path(r'^(?P<pk>\d+)/', CategoryParameterDetail.as_view(), name='api-part-category-parameter-detail'),
            re_path(r'^.*$', CategoryParameterList.as_view(), name='api-part-category-parameter-list'),
        ])),

        # Category detail endpoints
        path(r'<int:pk>/', include([

            re_path(r'^metadata/', MetadataView.as_view(), {'model': PartCategory}, name='api-part-category-metadata'),

            # PartCategory detail endpoint
            re_path(r'^.*$', CategoryDetail.as_view(), name='api-part-category-detail'),
        ])),

        path('', CategoryList.as_view(), name='api-part-category-list'),
    ])),

    # Base URL for PartTestTemplate API endpoints
    re_path(r'^test-template/', include([
        path(r'<int:pk>/', PartTestTemplateDetail.as_view(), name='api-part-test-template-detail'),
        path('', PartTestTemplateList.as_view(), name='api-part-test-template-list'),
    ])),

    # Base URL for PartAttachment API endpoints
    re_path(r'^attachment/', include([
        path(r'<int:pk>/', PartAttachmentDetail.as_view(), name='api-part-attachment-detail'),
        path('', PartAttachmentList.as_view(), name='api-part-attachment-list'),
    ])),

    # Base URL for part sale pricing
    re_path(r'^sale-price/', include([
        path(r'<int:pk>/', PartSalePriceDetail.as_view(), name='api-part-sale-price-detail'),
        re_path(r'^.*$', PartSalePriceList.as_view(), name='api-part-sale-price-list'),
    ])),

    # Base URL for part internal pricing
    re_path(r'^internal-price/', include([
        path(r'<int:pk>/', PartInternalPriceDetail.as_view(), name='api-part-internal-price-detail'),
        re_path(r'^.*$', PartInternalPriceList.as_view(), name='api-part-internal-price-list'),
    ])),

    # Base URL for PartRelated API endpoints
    re_path(r'^related/', include([
        path(r'<int:pk>/', PartRelatedDetail.as_view(), name='api-part-related-detail'),
        re_path(r'^.*$', PartRelatedList.as_view(), name='api-part-related-list'),
    ])),

    # Base URL for PartParameter API endpoints
    re_path(r'^parameter/', include([
        path('template/', include([
            re_path(r'^(?P<pk>\d+)/', include([
                re_path(r'^metadata/?', MetadataView.as_view(), {'model': PartParameter}, name='api-part-parameter-template-metadata'),
                re_path(r'^.*$', PartParameterTemplateDetail.as_view(), name='api-part-parameter-template-detail'),
            ])),
            re_path(r'^.*$', PartParameterTemplateList.as_view(), name='api-part-parameter-template-list'),
        ])),

        path(r'<int:pk>/', PartParameterDetail.as_view(), name='api-part-parameter-detail'),
        re_path(r'^.*$', PartParameterList.as_view(), name='api-part-parameter-list'),
    ])),

    # Part stocktake data
    re_path(r'^stocktake/', include([

        path(r'report/', include([
            path('generate/', PartStocktakeReportGenerate.as_view(), name='api-part-stocktake-report-generate'),
            re_path(r'^.*$', PartStocktakeReportList.as_view(), name='api-part-stocktake-report-list'),
        ])),

        path(r'<int:pk>/', PartStocktakeDetail.as_view(), name='api-part-stocktake-detail'),
        re_path(r'^.*$', PartStocktakeList.as_view(), name='api-part-stocktake-list'),
    ])),

    re_path(r'^thumbs/', include([
        path('', PartThumbs.as_view(), name='api-part-thumbs'),
        re_path(r'^(?P<pk>\d+)/?', PartThumbsUpdate.as_view(), name='api-part-thumbs-update'),
    ])),

    # BOM template
    re_path(r'^bom_template/?', views.BomUploadTemplate.as_view(), name='api-bom-upload-template'),

    path(r'<int:pk>/', include([

        # Endpoint for extra serial number information
        re_path(r'^serial-numbers/', PartSerialNumberDetail.as_view(), name='api-part-serial-number-detail'),

        # Endpoint for future scheduling information
        re_path(r'^scheduling/', PartScheduling.as_view(), name='api-part-scheduling'),

        re_path(r'^requirements/', PartRequirements.as_view(), name='api-part-requirements'),

        # Endpoint for duplicating a BOM for the specific Part
        re_path(r'^bom-copy/', PartCopyBOM.as_view(), name='api-part-bom-copy'),

        # Endpoint for validating a BOM for the specific Part
        re_path(r'^bom-validate/', PartValidateBOM.as_view(), name='api-part-bom-validate'),

        # Part metadata
        re_path(r'^metadata/', MetadataView.as_view(), {'model': Part}, name='api-part-metadata'),

        # Part pricing
        re_path(r'^pricing/', PartPricingDetail.as_view(), name='api-part-pricing'),

        # BOM download
        re_path(r'^bom-download/?', views.BomDownload.as_view(), name='api-bom-download'),

        # Old pricing endpoint
        re_path(r'^pricing2/', views.PartPricing.as_view(), name='part-pricing'),

        # Part detail endpoint
        re_path(r'^.*$', PartDetail.as_view(), name='api-part-detail'),
    ])),

    re_path(r'^.*$', PartList.as_view(), name='api-part-list'),
]

bom_api_urls = [

    re_path(r'^substitute/', include([

        # Detail view
        path(r'<int:pk>/', BomItemSubstituteDetail.as_view(), name='api-bom-substitute-detail'),

        # Catch all
        re_path(r'^.*$', BomItemSubstituteList.as_view(), name='api-bom-substitute-list'),
    ])),

    # BOM Item Detail
    path(r'<int:pk>/', include([
        re_path(r'^validate/?', BomItemValidate.as_view(), name='api-bom-item-validate'),
        re_path(r'^metadata/?', MetadataView.as_view(), {'model': BomItem}, name='api-bom-item-metadata'),
        re_path(r'^.*$', BomDetail.as_view(), name='api-bom-item-detail'),
    ])),

    # API endpoint URLs for importing BOM data
    re_path(r'^import/upload/', BomImportUpload.as_view(), name='api-bom-import-upload'),
    re_path(r'^import/extract/', BomImportExtract.as_view(), name='api-bom-import-extract'),
    re_path(r'^import/submit/', BomImportSubmit.as_view(), name='api-bom-import-submit'),

    # Catch-all
    re_path(r'^.*$', BomList.as_view(), name='api-bom-list'),
]
