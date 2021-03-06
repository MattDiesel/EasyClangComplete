"""Utilities for clang.

Attributes:
    log (logging.log): logger for this module
"""
import platform
import logging
import subprocess
import html

from os import path
from ..settings import settings_storage

log = logging.getLogger(__name__)


class ClangUtils:
    """Utils to help handling libclang, e.g. searching for it.

    Attributes:
        libclang_name (str): name of the libclang library file
        linux_suffixes (list): suffixes for linux
        osx_suffixes (list): suffixes for osx
        windows_suffixes (list): suffixes for windows
    """
    libclang_name = None

    windows_suffixes = ['.dll', '.lib']
    linux_suffixes = ['.so', '.so.1']
    osx_suffixes = ['.dylib']

    suffixes = {
        'Windows': windows_suffixes,
        'Linux': linux_suffixes,
        'Darwin': osx_suffixes
    }

    # MSYS2 has `clang.dll` instead of `libclang.dll`
    possible_filenames = {
        'Windows': ['libclang', 'clang'],
        'Linux': ['libclang-$version', 'libclang'],
        'Darwin': ['libclang']
    }

    @staticmethod
    def dir_from_output(output):
        """Get library directory based on the output of clang.

        Args:
            output (str): raw output from clang

        Returns:
            str: path to folder with libclang
        """
        log.debug(" real output: %s", output)
        if platform.system() == "Darwin":
            # [HACK] uh... I'm not sure why it happens like this...
            folder_to_search = path.join(output, '..', '..')
            log.debug(" folder to search: %s", folder_to_search)
            return folder_to_search
        elif platform.system() == "Windows":
            log.debug(" architecture: %s", platform.architecture())
            return path.normpath(output)
        elif platform.system() == "Linux":
            return path.normpath(path.dirname(output))
        return None

    @staticmethod
    def try_load_from_user_hint(libclang_path):
        """Load library hinted by the user.

        Args:
            libclang_path (str): full path to the libclang library file.

        Returns:
            str: folder of the libclang library or None if not found.
        """
        if path.exists(libclang_path):
            return path.dirname(libclang_path)

    @staticmethod
    def find_libclang_dir(clang_binary, libclang_path):
        """Find directory with libclang.

        Args:
            clang_binary (str): clang binary to call
            libclang_path (str): libclang path provided by user.
                Does not have to be valid.

        Returns:
            str: folder with libclang
        """
        stdin = None
        stderr = None
        log.debug(" platform: %s", platform.architecture())
        log.debug(" python version: %s", platform.python_version())
        current_system = platform.system()
        log.debug(" we are on '%s'", platform.system())
        log.debug(" user provided libclang_path: %s", libclang_path)
        # Get version string for help finding the proper libclang library on
        # Linux
        if libclang_path:
            # User thinks he knows better. Let him try his luck.
            libclang_dir = ClangUtils.try_load_from_user_hint(libclang_path)
            if libclang_dir:
                # It was found! No need to search any further!
                ClangUtils.libclang_name = path.basename(libclang_path)
                log.info(" using user-provided libclang: '%s'", libclang_path)
                return libclang_dir
        # If the user hint did not work, we look for it normally
        if current_system == "Linux":
            version_str = settings_storage.SettingsStorage.CLANG_VERSION[:-2]
        for suffix in ClangUtils.suffixes[current_system]:
            # pick a name for a file
            for name in ClangUtils.possible_filenames[current_system]:
                file = "{name}{suffix}".format(name=name, suffix=suffix)
                log.debug(" searching for: '%s'", file)
                startupinfo = None
                # let's find the library
                if platform.system() == "Darwin":
                    # [HACK]: wtf??? why does it not find libclang.dylib?
                    get_library_path_cmd = [clang_binary, "-print-file-name="]
                elif platform.system() == "Windows":
                    get_library_path_cmd = [clang_binary, "-print-prog-name="]
                    # Don't let console window pop-up briefly.
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                    startupinfo.wShowWindow = subprocess.SW_HIDE
                    stdin = subprocess.PIPE
                    stderr = subprocess.PIPE
                elif platform.system() == "Linux":
                    file = file.replace("$version", version_str)
                    get_library_path_cmd = [
                        clang_binary, "-print-file-name={}".format(file)]
                output = subprocess.check_output(
                    get_library_path_cmd,
                    stdin=stdin,
                    stderr=stderr,
                    startupinfo=startupinfo).decode('utf8').strip()
                log.debug(" libclang search output = '%s'", output)
                if output:
                    libclang_dir = ClangUtils.dir_from_output(output)
                    if path.isdir(libclang_dir):
                        full_libclang_path = path.join(libclang_dir, file)
                        if path.exists(full_libclang_path):
                            log.info(" found libclang library file: '%s'",
                                     full_libclang_path)
                            ClangUtils.libclang_name = file
                            return libclang_dir
                log.warning(" clang could not find '%s'", file)
        # if we haven't found anything there is nothing to return
        log.error(" no libclang found at all")
        return None

    @staticmethod
    def location_from_type(clangType):
        """Return location from type.

        Return proper location from type.
        Remove all inderactions like pointers etc.

        Args:
            clangType (cindex.Type): clang type.

        """
        cursor = clangType.get_declaration()
        if cursor and cursor.location and cursor.location.file:
            return cursor.location

        cursor = clangType.get_pointee().get_declaration()
        if cursor and cursor.location and cursor.location.file:
            return cursor.location

        return None

    @staticmethod
    def link_from_location(location, text):
        """Provide link to given cursor.

        Transforms SourceLocation object into html string.

        Args:
            location (Cursor.location): Current location.
            text (str): Text to be added as info.
        """
        result = ""
        if location and location.file and location.file.name:
            result += "<a href=\""
            result += location.file.name
            result += ":"
            result += str(location.line)
            result += ":"
            result += str(location.column)
            result += "\">" + text + "</a>"
        else:
            result += text
        return result

    @staticmethod
    def build_info_details(cursor, function_kinds_list):
        """Provide information about given cursor.

        Builds detailed information about cursor.

        Args:
            cursor (Cursor): Current cursor.

        """
        result = ""
        if cursor.result_type.spelling:
            cursor_type = cursor.result_type
        elif cursor.type.spelling:
            cursor_type = cursor.type
        else:
            log.warning("No spelling for type provided in info.")
            return ""
        result += '<b>Definition:</b><br>'
        if cursor.spelling != cursor.type.spelling:
            # Don't show duplicates if the user focuses type, not variable
            result += ClangUtils.link_from_location(
                ClangUtils.location_from_type(cursor_type),
                html.escape(cursor_type.spelling))
            result += ' '

        if cursor.location:
            result += ClangUtils.link_from_location(
                cursor.location,
                html.escape(cursor.spelling))
        else:
            result += html.escape(cursor.spelling)

        args = []
        for arg in cursor.get_arguments():
            if arg.spelling:
                args.append(arg.type.spelling + ' ' + arg.spelling)
            else:
                args.append(arg.type.spelling + ' ')

        if cursor.kind in function_kinds_list:
            result += '('
            if len(args):
                result += html.escape(', '.join(args))
            result += ')'

        if cursor.is_static_method():
            result = "static " + result
        if cursor.is_const_method():
            result += " const"

        if cursor.brief_comment:
            result += "<br><br><b>Brief documentation:</b><br>"
            result += "<div>" + cursor.brief_comment + "</div>"

        if cursor.raw_comment:
            html_raw_comment = ClangUtils.cleanup_comment(cursor.raw_comment)
            if len(html_raw_comment) > 0:
                result += "<br><b>Full Doxygen comment:</b>"
                result += "<br><div>" + html_raw_comment + "</div>"

        return result

    @staticmethod
    def cleanup_comment(raw_comment):
        """Cleanup raw doxygen comment."""
        lines = raw_comment.split('\n')
        clean_lines = []
        prev_line = ''
        is_brief_comment = False
        for line in lines:
            clean = line.strip()
            if clean.startswith('/'):
                clean = clean[3:]
            elif clean.startswith('*'):
                clean = clean[2:]
            clean = line[3:].strip()
            prev_line = clean
            if clean.startswith('@brief') or clean.startswith('/brief'):
                is_brief_comment = True
                continue
            if clean == '':
                is_brief_comment = False
            if clean == '' and prev_line == '':
                # We want to ignore trailing empty lines.
                continue
            if is_brief_comment:
                continue
            clean_lines.append(clean)
        return '<br>'.join(clean_lines)
