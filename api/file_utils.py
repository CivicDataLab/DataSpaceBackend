import mimetypes

import magic


def check_ext(file_object):
    ext_type = mimetypes.guess_type(file_object.name)[0]
    return ext_type


def check_mime_type(file_object):
    # with open(file_object.file) as mime_file:
    # print(type(file_object.file))
    mime_type = magic.from_buffer(file_object.read(), mime=True)
    # file_object.file.close()
    return mime_type


def file_validation(file_object, ext_object, mapping):
    ext_type = check_ext(ext_object)
    print("ext--", ext_type)
    mime_type = check_mime_type(file_object)
    print("mime--", mime_type)
    if ext_type and mime_type:
        if mapping.get(ext_type.lower()) == mapping.get(mime_type.lower()):
            return mime_type
        else:
            return None
    else:
        return None
