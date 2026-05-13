# SPDX-License-Identifier: GPL-3.0-or-later

import quart

from . import pages, quart_app, tagpoints


@quart_app.app.route("/tagpoints", methods=["GET", "POST"])
@quart_app.wrap_sync_route_handler
def tagpoints_index(*path, show_advanced="", **data):
    # This page could be slow because of the db stuff, so we restrict it more
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    page_number = int(data.get("pageNumber", 0))
    search_filter = data.get("searchFilter", "").strip()

    # Filter tags by search term
    filtered_tags = [
        tag
        for tag in tagpoints.allTagsAtomic.keys()
        if search_filter.lower() in tag.lower()
    ]
    filtered_tags_sorted = sorted(filtered_tags)

    # Paginate results (250 per page)
    paginated_tags = filtered_tags_sorted[
        page_number * 250 : (page_number + 1) * 250
    ]

    # Build tag data for template
    tags_data = []
    for tag_name in paginated_tags:
        if tag_name not in tagpoints.allTags:
            continue

        tag = tagpoints.allTagsAtomic[tag_name]()
        if tag is None:
            tags_data.append(
                {
                    "name": tag_name,
                    "type": "deleted",
                    "value": "DELETED",
                    "alerts_count": 0,
                }
            )
        elif isinstance(tag, tagpoints.NumericTagPointClass):
            tags_data.append(
                {
                    "name": tag_name,
                    "type": "numeric",
                    "value": tag.last_value,
                    "alerts_count": len(tag.get_alerts()),
                }
            )
        elif isinstance(tag, tagpoints.StringTagPointClass):
            tags_data.append(
                {
                    "name": tag_name,
                    "type": "string",
                    "value": str(tag.last_value)[:32],
                    "alerts_count": len(tag.get_alerts()),
                }
            )
        elif isinstance(tag, tagpoints.ObjectTagPointClass):
            tags_data.append(
                {
                    "name": tag_name,
                    "type": "object",
                    "value": str(tag.last_value)[:32],
                    "alerts_count": len(tag.get_alerts()),
                }
            )
        elif isinstance(tag, tagpoints.BinaryTagPointClass):
            tags_data.append(
                {
                    "name": tag_name,
                    "type": "binary",
                    "value": "Value is binary data",
                    "alerts_count": len(tag.get_alerts()),
                }
            )

    extra_url_stuff = ""
    if quart.request.args.get("kaithem_disable_header", 0):
        extra_url_stuff = "?kaithem_disable_header=true"

    total_pages = int(len(filtered_tags_sorted) / 250) + 1
    page_numbers = list(range(total_pages))

    return pages.render_jinja_template(
        "settings/tagpoints.j2.html",
        page_number=page_number,
        search_filter=search_filter,
        tags_data=tags_data,
        extra_url_stuff=extra_url_stuff,
        page_numbers=page_numbers,
        total_pages=total_pages,
    )


@quart_app.app.route("/tagpoints/<path:path>", methods=["GET", "POST"])
def specific_tagpoint(path):
    path = path.split("/")
    # This page could be slow because of the db stuff, so we restrict it more
    try:
        pages.require("system_admin")
    except PermissionError:
        return pages.loginredirect(pages.geturl())

    tn = "/".join(path)
    if (not tn.startswith("=")) and not tn.startswith("/"):
        tn = "/" + tn
    if tagpoints.normalize_tag_name(tn) not in tagpoints.allTags:
        raise ValueError("This tag does not exist")
    return pages.get_template("settings/tagpoint.html").render(
        tagName=tn,
        data=quart.request.args,
        show_advanced=True,
        module="",
        resource="",
    )
