import gkeepapi
import re
import schoolopy
import time
import yaml


def main():
    """
    Bring Schoology posts into Google Keep as notes.

    Returns:
        Number of posts newly converted.
    """
    # Retrieve credentials
    with open('config.yaml', 'r') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)

    school_url = config['school_url']
    limit = config['num_posts']
    sc = schoolopy.Schoology(schoolopy.Auth(config['s_key'],
                                            config['s_secret']))

    count = 0
    keep = gkeepapi.Keep()
    keep.login(config['g_email'], config['g_password'])

    # Get Schoology feed with attachments
    feed = (schoolopy.Update(raw)
            for raw in sc._get(
                f'recent?with_attachments=1&&limit={limit}')['update'])

    # Retrieve last ran timestamp
    try:
        with open('data.txt', 'r') as f:
            last_ran = int(f.read())
    # Script has never been ran before
    except FileNotFoundError:
        last_ran = 1
    # Store new timestamps
    with open('data.txt', 'w') as f:
        f.write(str(int(time.time())))

    for post in feed:
        modified = False
        comments = None
        body = ''
        if post.num_comments > 0:
            # Get comments if post is in a group
            if post.realm == "group":
                comments = sc.get_group_update_comments(post.id,
                                                        post.group_id)
            # Get comments if post is in a course
            elif post.realm == "section":
                comments = sc.get_section_update_comments(post.id,
                                                          post.section_id)
            else:
                continue

            # The note has already been added
            if post.created < last_ran:
                for comment in comments:
                    # But there has been a new comment added to the post
                    if comment.created >= last_ran:
                        modified = True
                        break

        if post.created >= last_ran or modified:
            # Delete non-breaking space and carriage return
            body = post.body.replace(u'\r', '').replace(u'\xa0', '') + '\n\n'
            # Replaces any amount of newlines into only one empty newline
            body = re.sub(r'\n+', '\n\n', body)

            # Title will be the author of the post
            title = sc.get_user(post.uid).name_display

            if hasattr(post, 'attachments'):
                attachments = post.attachments

                # Leave link to original post if post attaches embeds or videos
                if 'embeds' in attachments or 'videos' in attachments:
                    body += ("An embed or video is attached:\n"
                             f"https://{school_url}/group/"
                             f"{post.group_id}/update/{post.id}\n\n")

                # Leave link to attached links
                if 'links' in attachments:
                    for link in attachments['links']['link']:
                        body += f"{link['title']} (link)\n{link['url']}\n\n"

                if 'files' in attachments:
                    for file in attachments['files']['file']:
                        # Leave link to preview attached images
                        if file['converted_type'] == 3:
                            body += (f"{file['title']} (image)\n"
                                     f"https://{school_url}/attachment/"
                                     f"{file['id']}/image/"
                                     "lightbox_preview\n\n")
                        # Leave link to preview attached files
                        else:
                            body += (f"{file['title']} (file)\n"
                                     f"https://{school_url}/attachment/"
                                     f"{file['id']}/docviewer\n\n")

            # Add comments, if any, to bottom of note
            body_comment = ''
            if post.num_comments > 0:
                for comment in comments:
                    body_comment += (
                        f"{sc.get_user(comment.uid).name_display} "
                        f"(comment)\n{comment.comment}\n\n")

            # Add new comment to old note and bring out of archive
            if modified:
                old_notes = list(keep.find(query=body.strip('\n')))
                if len(old_notes) == 1:
                    old_note = old_notes[0]
                    body = (body + body_comment).strip(u'\n')
                    old_note.text = body
                    old_note.archived = False

            else:
                body = (body + body_comment).strip(u'\n')
                note = keep.createNote(title, body)

                # Label should be the group/course the post was made in
                if post.realm == 'group':
                    group_name = sc.get_group(post.group_id).title
                elif post.realm == 'section':
                    group_name = sc.get_section(post.section_id).course_title
                else:
                    group_name = "Unkown"

                label = keep.findLabel(group_name)
                # Add group label if exists
                if label:
                    note.labels.add(label)
                # Create new group label if not
                else:
                    note.labels.add(keep.createLabel(group_name))
                count += 1

    keep.sync()
    return count


if __name__ == '__main__':
    print("Reading posts...")
    print(f"Added {main()} new posts")
