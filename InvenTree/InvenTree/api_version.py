"""InvenTree API version information."""


# InvenTree API version
INVENTREE_API_VERSION = 105

"""
Increment this API version number whenever there is a significant change to the API that any clients need to know about

v105 -> 2023-03-31 : https://github.com/inventree/InvenTree/pull/4543
    - Adds API endpoints for status label information on various models

v104 -> 2023-03-23 : https://github.com/inventree/InvenTree/pull/4488
    - Adds various endpoints for new "ReturnOrder" models
    - Adds various endpoints for new "ReturnOrderReport" templates
    - Exposes API endpoints for "Contact" model

v103 -> 2023-03-17 : https://github.com/inventree/InvenTree/pull/4410
    - Add metadata to several more models

v102 -> 2023-03-18 : https://github.com/inventree/InvenTree/pull/4505
- Adds global search API endpoint for consolidated search results

v101 -> 2023-03-07 : https://github.com/inventree/InvenTree/pull/4462
    - Adds 'total_in_stock' to Part serializer, and supports API ordering

v100 -> 2023-03-04 : https://github.com/inventree/InvenTree/pull/4452
     - Adds bulk delete of PurchaseOrderLineItems to API

v99 -> 2023-03-03 : https://github.com/inventree/InvenTree/pull/4445
    - Adds sort by "responsible" to PurchaseOrderAPI

v98 -> 2023-02-24 : https://github.com/inventree/InvenTree/pull/4408
    - Adds "responsible" filter to Build API

v97 -> 2023-02-20 : https://github.com/inventree/InvenTree/pull/4377
    - Adds "external" attribute to StockLocation model

v96 -> 2023-02-16 : https://github.com/inventree/InvenTree/pull/4345
    - Adds stocktake report generation functionality

v95 -> 2023-02-16 : https://github.com/inventree/InvenTree/pull/4346
    - Adds "CompanyAttachment" model (and associated API endpoints)

v94 -> 2023-02-10 : https://github.com/inventree/InvenTree/pull/4327
    - Adds API endpoints for the "Group" auth model

v93 -> 2023-02-03 : https://github.com/inventree/InvenTree/pull/4300
    - Adds extra information to the currency exchange endpoint
    - Adds API endpoint for manually updating exchange rates

v92 -> 2023-02-02 : https://github.com/inventree/InvenTree/pull/4293
    - Adds API endpoint for currency exchange information

v91 -> 2023-01-31 : https://github.com/inventree/InvenTree/pull/4281
    - Improves the API endpoint for creating new Part instances

v90 -> 2023-01-25 : https://github.com/inventree/InvenTree/pull/4186/files
    - Adds a dedicated endpoint to activate a plugin

v89 -> 2023-01-25 : https://github.com/inventree/InvenTree/pull/4214
    - Adds updated field to SupplierPart API
    - Adds API date orddering for supplier part list

v88 -> 2023-01-17: https://github.com/inventree/InvenTree/pull/4225
    - Adds 'priority' field to Build model and api endpoints

v87 -> 2023-01-04 : https://github.com/inventree/InvenTree/pull/4067
    - Add API date filter for stock table on Expiry date

v86 -> 2022-12-22 : https://github.com/inventree/InvenTree/pull/4069
    - Adds API endpoints for part stocktake

v85 -> 2022-12-21 : https://github.com/inventree/InvenTree/pull/3858
    - Add endpoints serving ICS calendars for purchase and sales orders through API

v84 -> 2022-12-21: https://github.com/inventree/InvenTree/pull/4083
    - Add support for listing PO, BO, SO by their reference

v83 -> 2022-11-19 : https://github.com/inventree/InvenTree/pull/3949
    - Add support for structural Stock locations

v82 -> 2022-11-16 : https://github.com/inventree/InvenTree/pull/3931
    - Add support for structural Part categories

v81 -> 2022-11-08 : https://github.com/inventree/InvenTree/pull/3710
    - Adds cached pricing information to Part API
    - Adds cached pricing information to BomItem API
    - Allows Part and BomItem list endpoints to be filtered by 'has_pricing'
    - Remove calculated 'price_string' values from API endpoints
    - Allows PurchaseOrderLineItem API endpoint to be filtered by 'has_pricing'
    - Allows SalesOrderLineItem API endpoint to be filtered by 'has_pricing'
    - Allows SalesOrderLineItem API endpoint to be filtered by 'order_status'
    - Adds more information to SupplierPriceBreak serializer

v80 -> 2022-11-07 : https://github.com/inventree/InvenTree/pull/3906
    - Adds 'barcode_hash' to Part API serializer
    - Adds 'barcode_hash' to StockLocation API serializer
    - Adds 'barcode_hash' to SupplierPart API serializer

v79 -> 2022-11-03 : https://github.com/inventree/InvenTree/pull/3895
    - Add metadata to Company

v78 -> 2022-10-25 : https://github.com/inventree/InvenTree/pull/3854
    - Make PartCategory to be filtered by name and description

v77 -> 2022-10-12 : https://github.com/inventree/InvenTree/pull/3772
    - Adds model permission checks for barcode assignment actions

v76 -> 2022-09-10 : https://github.com/inventree/InvenTree/pull/3640
    - Refactor of barcode data on the API
    - StockItem.uid renamed to StockItem.barcode_hash

v75 -> 2022-09-05 : https://github.com/inventree/InvenTree/pull/3644
    - Adds "pack_size" attribute to SupplierPart API serializer

v74 -> 2022-08-28 : https://github.com/inventree/InvenTree/pull/3615
    - Add confirmation field for completing PurchaseOrder if the order has incomplete lines
    - Add confirmation field for completing SalesOrder if the order has incomplete lines

v73 -> 2022-08-24 : https://github.com/inventree/InvenTree/pull/3605
    - Add 'description' field to PartParameterTemplate model

v72 -> 2022-08-18 : https://github.com/inventree/InvenTree/pull/3567
    - Allow PurchaseOrder to be duplicated via the API

v71 -> 2022-08-18 : https://github.com/inventree/InvenTree/pull/3564
    - Updates to the "part scheduling" API endpoint

v70 -> 2022-08-02 : https://github.com/inventree/InvenTree/pull/3451
    - Adds a 'depth' parameter to the PartCategory list API
    - Adds a 'depth' parameter to the StockLocation list API

v69 -> 2022-08-01 : https://github.com/inventree/InvenTree/pull/3443
    - Updates the PartCategory list API:
        - Improve query efficiency: O(n) becomes O(1)
        - Rename 'parts' field to 'part_count'
    - Updates the StockLocation list API:
        - Improve query efficiency: O(n) becomes O(1)

v68 -> 2022-07-27 : https://github.com/inventree/InvenTree/pull/3417
    - Allows SupplierPart list to be filtered by SKU value
    - Allows SupplierPart list to be filtered by MPN value

v67 -> 2022-07-25 : https://github.com/inventree/InvenTree/pull/3395
    - Adds a 'requirements' endpoint for Part instance
    - Provides information on outstanding order requirements for a given part

v66 -> 2022-07-24 : https://github.com/inventree/InvenTree/pull/3393
    - Part images can now be downloaded from a remote URL via the API
    - Company images can now be downloaded from a remote URL via the API

v65 -> 2022-07-15 : https://github.com/inventree/InvenTree/pull/3335
    - Annotates 'in_stock' quantity to the SupplierPart API

v64 -> 2022-07-08 : https://github.com/inventree/InvenTree/pull/3310
    - Annotate 'on_order' quantity to BOM list API
    - Allow BOM List API endpoint to be filtered by "on_order" parameter

v63 -> 2022-07-06 : https://github.com/inventree/InvenTree/pull/3301
    - Allow BOM List API endpoint to be filtered by "available_stock" paramater

v62 -> 2022-07-05 : https://github.com/inventree/InvenTree/pull/3296
    - Allows search on BOM List API endpoint
    - Allows ordering on BOM List API endpoint

v61 -> 2022-06-12 : https://github.com/inventree/InvenTree/pull/3183
    - Migrate the "Convert Stock Item" form class to use the API
    - There is now an API endpoint for converting a stock item to a valid variant

v60 -> 2022-06-08 : https://github.com/inventree/InvenTree/pull/3148
    - Add availability data fields to the SupplierPart model

v59 -> 2022-06-07 : https://github.com/inventree/InvenTree/pull/3154
    - Adds further improvements to BulkDelete mixin class
    - Fixes multiple bugs in custom OPTIONS metadata implementation
    - Adds 'bulk delete' for Notifications

v58 -> 2022-06-06 : https://github.com/inventree/InvenTree/pull/3146
    - Adds a BulkDelete API mixin class for fast, safe deletion of multiple objects with a single API request

v57 -> 2022-06-05 : https://github.com/inventree/InvenTree/pull/3130
    - Transfer PartCategoryTemplateParameter actions to the API

v56 -> 2022-06-02 : https://github.com/inventree/InvenTree/pull/3123
    - Expose the PartParameterTemplate model to use the API

v55 -> 2022-06-02 : https://github.com/inventree/InvenTree/pull/3120
    - Converts the 'StockItemReturn' functionality to make use of the API

v54 -> 2022-06-02 : https://github.com/inventree/InvenTree/pull/3117
    - Adds 'available_stock' annotation on the SalesOrderLineItem API
    - Adds (well, fixes) 'overdue' annotation on the SalesOrderLineItem API

v53 -> 2022-06-01 : https://github.com/inventree/InvenTree/pull/3110
    - Adds extra search fields to the BuildOrder list API endpoint

v52 -> 2022-05-31 : https://github.com/inventree/InvenTree/pull/3103
    - Allow part list API to be searched by supplier SKU

v51 -> 2022-05-24 : https://github.com/inventree/InvenTree/pull/3058
    - Adds new fields to the SalesOrderShipment model

v50 -> 2022-05-18 : https://github.com/inventree/InvenTree/pull/2912
    - Implement Attachments for manufacturer parts

v49 -> 2022-05-09 : https://github.com/inventree/InvenTree/pull/2957
    - Allows filtering of plugin list by 'active' status
    - Allows filtering of plugin list by 'mixin' support
    - Adds endpoint to "identify" or "locate" stock items and locations (using plugins)

v48 -> 2022-05-12 : https://github.com/inventree/InvenTree/pull/2977
    - Adds "export to file" functionality for PurchaseOrder API endpoint
    - Adds "export to file" functionality for SalesOrder API endpoint
    - Adds "export to file" functionality for BuildOrder API endpoint

v47 -> 2022-05-10 : https://github.com/inventree/InvenTree/pull/2964
    - Fixes barcode API error response when scanning a StockItem which does not exist
    - Fixes barcode API error response when scanning a StockLocation which does not exist

v46 -> 2022-05-09
    - Fixes read permissions on settings API
    - Allows non-staff users to read global settings via the API

v45 -> 2022-05-08 : https://github.com/inventree/InvenTree/pull/2944
    - Settings are now accessed via the API using their unique key, not their PK
    - This allows the settings to be accessed without prior knowledge of the PK

v44 -> 2022-05-04 : https://github.com/inventree/InvenTree/pull/2931
    - Converting more server-side rendered forms to the API
    - Exposes more core functionality to API endpoints

v43 -> 2022-04-26 : https://github.com/inventree/InvenTree/pull/2875
    - Adds API detail endpoint for PartSalePrice model
    - Adds API detail endpoint for PartInternalPrice model

v42 -> 2022-04-26 : https://github.com/inventree/InvenTree/pull/2833
    - Adds variant stock information to the Part and BomItem serializers

v41 -> 2022-04-26
    - Fixes 'variant_of' filter for Part list endpoint

v40 -> 2022-04-19
    - Adds ability to filter StockItem list by "tracked" parameter
        - This checks the serial number or batch code fields

v39 -> 2022-04-18
    - Adds ability to filter StockItem list by "has_batch" parameter

v38 -> 2022-04-14 : https://github.com/inventree/InvenTree/pull/2828
    - Adds the ability to include stock test results for "installed items"

v37 -> 2022-04-07 : https://github.com/inventree/InvenTree/pull/2806
    - Adds extra stock availability information to the BomItem serializer

v36 -> 2022-04-03
    - Adds ability to filter part list endpoint by unallocated_stock argument

v35 -> 2022-04-01 : https://github.com/inventree/InvenTree/pull/2797
    - Adds stock allocation information to the Part API
    - Adds calculated field for "unallocated_quantity"

v34 -> 2022-03-25
    - Change permissions for "plugin list" API endpoint (now allows any authenticated user)

v33 -> 2022-03-24
    - Adds "plugins_enabled" information to root API endpoint

v32 -> 2022-03-19
    - Adds "parameters" detail to Part API endpoint (use &parameters=true)
    - Adds ability to filter PartParameterTemplate API by Part instance
    - Adds ability to filter PartParameterTemplate API by PartCategory instance

v31 -> 2022-03-14
    - Adds "updated" field to SupplierPriceBreakList and SupplierPriceBreakDetail API endpoints

v30 -> 2022-03-09
    - Adds "exclude_location" field to BuildAutoAllocation API endpoint
    - Allows BuildItem API endpoint to be filtered by BomItem relation

v29 -> 2022-03-08
    - Adds "scheduling" endpoint for predicted stock scheduling information

v28 -> 2022-03-04
    - Adds an API endpoint for auto allocation of stock items against a build order
    - Ref: https://github.com/inventree/InvenTree/pull/2713

v27 -> 2022-02-28
    - Adds target_date field to individual line items for purchase orders and sales orders

v26 -> 2022-02-17
    - Adds API endpoint for uploading a BOM file and extracting data

v25 -> 2022-02-17
    - Adds ability to filter "part" list endpoint by "in_bom_for" argument

v24 -> 2022-02-10
    - Adds API endpoint for deleting (cancelling) build order outputs

v23 -> 2022-02-02
    - Adds API endpoints for managing plugin classes
    - Adds API endpoints for managing plugin settings

v22 -> 2021-12-20
    - Adds API endpoint to "merge" multiple stock items

v21 -> 2021-12-04
    - Adds support for multiple "Shipments" against a SalesOrder
    - Refactors process for stock allocation against a SalesOrder

v20 -> 2021-12-03
    - Adds ability to filter POLineItem endpoint by "base_part"
    - Adds optional "order_detail" to POLineItem list endpoint

v19 -> 2021-12-02
    - Adds the ability to filter the StockItem API by "part_tree"
    - Returns only stock items which match a particular part.tree_id field

v18 -> 2021-11-15
    - Adds the ability to filter BomItem API by "uses" field
    - This returns a list of all BomItems which "use" the specified part
    - Includes inherited BomItem objects

v17 -> 2021-11-09
    - Adds API endpoints for GLOBAL and USER settings objects
    - Ref: https://github.com/inventree/InvenTree/pull/2275

v16 -> 2021-10-17
    - Adds API endpoint for completing build order outputs

v15 -> 2021-10-06
    - Adds detail endpoint for SalesOrderAllocation model
    - Allows use of the API forms interface for adjusting SalesOrderAllocation objects

v14 -> 2021-10-05
    - Stock adjustment actions API is improved, using native DRF serializer support
    - However adjustment actions now only support 'pk' as a lookup field

v13 -> 2021-10-05
    - Adds API endpoint to allocate stock items against a BuildOrder
    - Updates StockItem API with improved filtering against BomItem data

v12 -> 2021-09-07
    - Adds API endpoint to receive stock items against a PurchaseOrder

v11 -> 2021-08-26
    - Adds "units" field to PartBriefSerializer
    - This allows units to be introspected from the "part_detail" field in the StockItem serializer

v10 -> 2021-08-23
    - Adds "purchase_price_currency" to StockItem serializer
    - Adds "purchase_price_string" to StockItem serializer
    - Purchase price is now writable for StockItem serializer

v9  -> 2021-08-09
    - Adds "price_string" to part pricing serializers

v8  -> 2021-07-19
    - Refactors the API interface for SupplierPart and ManufacturerPart models
    - ManufacturerPart objects can no longer be created via the SupplierPart API endpoint

v7  -> 2021-07-03
    - Introduced the concept of "API forms" in https://github.com/inventree/InvenTree/pull/1716
    - API OPTIONS endpoints provide comprehensive field metedata
    - Multiple new API endpoints added for database models

v6  -> 2021-06-23
    - Part and Company images can now be directly uploaded via the REST API

v5  -> 2021-06-21
    - Adds API interface for manufacturer part parameters

v4  -> 2021-06-01
    - BOM items can now accept "variant stock" to be assigned against them
    - Many slight API tweaks were needed to get this to work properly!

v3  -> 2021-05-22:
    - The updated StockItem "history tracking" now uses a different interface

"""
