import os
import json
from .publisher import Publisher
from .injector import Injector
from .includer import Includer


class Error(Exception):
    pass


class Bower(object):
    """Contains a bunch of bower_components directories.
    """
    def __init__(self, publisher_signature='bowerstatic'):
        self.publisher_signature = publisher_signature
        self._components_directories = {}
        self._local = {}

    def components(self, name, path):
        if name in self._components_directories:
            raise Error("Duplicate name for components directory: %s" % name)
        result = ComponentsDirectory(self, name, path)
        self._components_directories[name] = result
        return result

    def local_components(self, name, components_directory):
        if name in self._local:
            raise Error("Duplicate name for local components: %s" % name)
        result = LocalComponents(self, name, components_directory)
        self._local[name] = result
        return result

    def wrap(self, wsgi):
        return self.publisher(self.injector(wsgi))

    def publisher(self, wsgi):
        return Publisher(self, wsgi)

    def injector(self, wsgi):
        return Injector(self, wsgi)

    def get_filename(self, bower_components_name,
                     package_name, package_version, file_path):
        components_directory = self._components_directories.get(
            bower_components_name)
        if components_directory is None:
            return None
        return components_directory.get_filename(package_name,
                                                 package_version,
                                                 file_path)


class ComponentCollection(object):
    def __init__(self, bower, name):
        self.bower = bower
        self.name = name
        self._resources = {}

    def includer(self, environ):
        return Includer(self.bower, self, environ)

    def resource(self, path, dependencies=None):
        dependencies = dependencies or []
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        result = Resource(self.bower, self, path, dependencies)
        self._resources[path] = result
        return result

class ComponentsDirectory(object):
    def __init__(self, bower, name, path):
        self.bower = bower
        self.name = name
        self.path = path
        self._packages = load_packages(path)
        self._resources = {}
        for package in self._packages.values():
            package.create_main_resource(self)

    def includer(self, environ):
        return Includer(self.bower, self, environ)

    def resource(self, path, dependencies=None):
        dependencies = dependencies or []
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        result = Resource(self.bower, self, path, dependencies)
        self._resources[path] = result
        return result

    def get_resource(self, path):
        return self._resources.get(path)

    def path_to_resource(self, path_or_resource):
        if isinstance(path_or_resource, basestring):
            return self.resource(path_or_resource)
        else:
            resource = path_or_resource
            assert resource.components_directory is self
        return resource

    def get_package(self, package_name):
        return self._packages.get(package_name)

    def get_filename(self, package_name, package_version, file_path):
        package = self._packages.get(package_name)
        if package is None:
            return None
        return package.get_filename(package_version, file_path)


class LocalComponents(object):
    def __init__(self, bower, name, components):
        self.bower = bower
        self.name = name
        self._components = components
        self._local = {}
        self._resources = {}

    def component(self, path, version):
        result = LocalComponent(path, version)
        if result.name in self._local:
            raise Error("Duplicate name for local component: %s" % name)
        self._local[result.name] = result
        return result

    def includer(self, environ):
        return self._components.includer(environ)

    def resource(self, path, dependencies=None):
        dependencies = dependencies or []
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        resource = self._components.get_resource(path)
        if resource is not None:
            return resource
        result = Resource(self.bower, self, path, dependencies)
        self._resources[path] = result
        return result

    def get_resource(self, path):
        resource = self._resources.get(path)
        if resource is not None:
            return resource
        return self._components.get_resource(path)

    def path_to_resource(self, path_or_resource):
        if isinstance(path_or_resource, basestring):
            return self.resource(path_or_resource)
        else:
            resource = path_or_resource
        return resource

    def get_package(self, package_name):
        local_component = self._local.get(package_name)
        if local_component is not None:
            return local_component.package
        return self._components.get_package(package_name)

    def get_filename(self, package_name, package_version, file_path):
        package = self._packages.get(package_name)
        if package is None:
            return None
        return package.get_filename(package_version, file_path)


class LocalComponent(object):
    def __init__(self, path, version):
        self.path = path
        self.version = version
        self.package = load_package(path, 'bower.json')
        self.name = self.package.name

def load_packages(path):
    result = {}
    for package_path in os.listdir(path):
        fullpath = os.path.join(path, package_path)
        if not os.path.isdir(fullpath):
            continue
        package = load_package(fullpath, '.bower.json')
        result[package.name] = package
    return result


def load_package(path, bower_filename):
    bower_json_filename = os.path.join(path, bower_filename)
    with open(bower_json_filename, 'rb') as f:
        data = json.load(f)
    if isinstance(data['main'], list):
        main = data['main'][0]
    else:
        main = data['main']
    dependencies = data.get('dependencies')
    if dependencies is None:
        dependencies = {}
    return Package(path,
                   data['name'],
                   data['version'],
                   main,
                   dependencies)


class Package(object):
    def __init__(self, path, name, version, main, dependencies):
        self.path = path
        self.name = name
        self.version = version
        self.main = main
        self.dependencies = dependencies

    def create_main_resource(self, components_directory):
        # if the resource was already created, return it
        resource = components_directory.get_resource(self.name)
        if resource is not None:
            return resource
        # create a main resource for all dependencies
        dependencies = []
        for package_name in self.dependencies.keys():
            package = components_directory.get_package(package_name)
            dependencies.append(
                package.create_main_resource(components_directory))
        # depend on those main resources in this resource
        return components_directory.resource(
            self.name, dependencies=dependencies)

    def get_filename(self, version, file_path):
        if version != self.version:
            return None
        filename = os.path.abspath(os.path.join(self.path, file_path))
        # sanity check to prevent file_path to escape from path
        if not filename.startswith(self.path):
            return None
        return filename


class Resource(object):
    def __init__(self, bower, components_directory, path, dependencies):
        self.bower = bower
        self.components_directory = components_directory
        self.path = path
        self.dependencies = [
            components_directory.path_to_resource(dependency) for
            dependency in dependencies]

        parts = path.split('/', 1)
        if len(parts) == 2:
            package_name, file_path = parts
        else:
            package_name = parts[0]
            file_path = None
        self.package = self.components_directory.get_package(package_name)
        if self.package is None:
            raise Error(
                "Package %s not known in components directory %s (%s)" % (
                    package_name, components_directory.name,
                    components_directory.path))
        if file_path is None:
            file_path = self.package.main
        self.file_path = file_path
        dummy, self.ext = os.path.splitext(file_path)

    def url(self):
        parts = [
            self.bower.publisher_signature,
            self.components_directory.name,
            self.package.name,
            self.package.version,
            self.file_path]
        return '/' + '/'.join(parts)
