"""Build configuration stuff."""

import collections
import os
import shutil
import subprocess
import sys
import time

try:
  isinstance("hi", basestring)
except NameError:
  basestring = str


class BuildPath(object):
  @staticmethod
  def expand(value, rootDir, buildDir):
    if isinstance(value, BuildPath):
      value = value.toString(rootDir, buildDir)

    return value

  @staticmethod
  def extract(value):
    if isinstance(value, BuildPath):
      value = value._value

    return value

  def __init__(self, value, atRoot = True):
    self._value = value
    self._atRoot = atRoot

  def __hash__(self):
    return hash(self._value) ^ hash(self._atRoot)

  def __eq__(self, rhs):
    return rhs and isinstance(
        rhs, BuildPath
    ) and self._value == rhs._value and self._atRoot == rhs._atRoot

  def __ne__(self, rhs):
    return not self.__eq__(rhs)

  def toString(self, rootDir, buildDir):
    return os.path.join(rootDir if self._atRoot else buildDir, self._value)


class BuildDeps(object):
  def __init__(self, deps, implicit = None, order = None):
    self._deps = frozenset(deps or ())
    self._implicit = frozenset(implicit or ())
    self._order = frozenset(order or ())

  def _emit(self, stream, rootDir, buildDir):
    parts = list()

    if len(self._deps):
      parts.extend([
          BuildPath.expand(dep, rootDir, buildDir) for dep in self._deps
      ])

    if len(self._implicit):
      parts.append("|")

      parts.extend([
          BuildPath.expand(dep, rootDir, buildDir) for dep in self._implicit
      ])

    if len(self._order):
      parts.append("||")

      parts.extend([
          BuildPath.expand(dep, rootDir, buildDir) for dep in self._order
      ])

    stream.write(" ".join(parts))


class BuildVarHost(object):
  def __init__(self):
    self._vars = dict()

  def _keyValid(self, key):
    return True

  def _emitVar(self, stream, rootDir, buildDir, key, value, prefix):
    stream.write(
        "%s%s = %s\n" %
        (prefix, key, BuildPath.expand(value, rootDir, buildDir))
    )

  def _emitVars(self, stream, rootDir, buildDir, prefix, specials = None):
    if specials is None: specials = {}

    if len(specials) == 0 and len(self._vars) == 0: return False

    for key in specials:
      self._emitVar(stream, rootDir, buildDir, key, specials[key], prefix)

    if len(specials) > 0 and len(self._vars) > 0:
      stream.write("\n")

    for key in self._vars:
      if not self._keyValid(key):
        raise ValueError("Invalid key %s" % (key))

      self._emitVar(stream, rootDir, buildDir, key, self._vars[key], prefix)

    return True

  def set(self, **kwargs):
    for key in kwargs:
      self._vars[key] = kwargs[key]

  def unset(self, *args):
    for key in args:
      self._vars.pop(key)


class Build(BuildVarHost):
  def __init__(self):
    BuildVarHost.__init__(self)
    self._edges = list()
    self._ruleList = list()
    self._rules = dict()
    self._targets = dict()
    self._defaults = set()

    self._rules["phony"] = BuildPhonyRule(self)

  def deps(self, *args):
    return BuildDeps(*args)

  # edge(targets, [rule,] deps, [default])
  def edge(self, *args):
    targets = args[0]
    rule = None
    deps = args[1]
    default = False

    if len(args) == 2: pass
    elif len(args) == 3:
      if isinstance(
          args[2],
          (basestring, BuildPath, BuildDeps, collections.Iterable)
      ):
        rule = deps
        deps = args[2]
      else:
        default = args[2]
    elif len(args) == 4:
      rule = deps
      deps = args[2]
      default = args[3]
    else:
      raise ValueError("Invalid arguments.")

    if isinstance(targets, (basestring, BuildPath)): targets = targets,
    if isinstance(deps, (basestring, BuildPath)):
      deps = BuildDeps((deps, ), (), ())

    if not isinstance(deps, BuildDeps): deps = BuildDeps(deps, (), ())

    targetset = frozenset(
        [os.path.splitext(BuildPath.extract(tgt))[1] for tgt in targets]
    )

    if targetset in self._edges:
      raise ValueError("Target set already registered.")

    idx = len(self._edges)
    self._edges.append(BuildEdge(self, targets, deps))

    if rule is not None: self._edges[idx].setRule(rule)

    if default: self._defaults.add(idx)

    return self._edges[idx]

  def edges(self, *args):
    for arg in args:
      self.edge(*arg)

  def _emit(self, stream, rootDir, buildDir):
    usedRules = set()

    rootdirName = "rootdir"
    builddirName = "builddir"

    if self._emitVars(
        stream, rootDir, buildDir, "",
        {rootdirName: rootDir, builddirName: buildDir}
    ):
      stream.write("\n")

    rootdirName = "$%s" % (rootdirName)
    builddirName = "$%s" % (builddirName)

    for edge in self._edges:
      usedRules.add(edge.getRule())

    for rule in self._ruleList:
      if rule in usedRules and rule._emit(stream, rootdirName, builddirName):
        stream.write("\n")

    for edge in self._edges:
      edge._emit(stream, rootdirName, builddirName)

    if len(self._defaults):
      stream.write(
          "\ndefault %s\n" % (
              " ".join([
                  self._edges[idx].expandName(rootdirName, builddirName)
                  for idx in self._defaults
              ])
          )
      )

  def _keyValid(self, key):
    return key != "builddir"

  def rule(self, name, **kwargs):
    if name in self._rules:
      raise ValueError("Rule name already registered.")

    rule = BuildRule(self, name)
    self._ruleList.append(rule)
    self._rules[name] = rule

    if "targets" in kwargs:
      if "deps" not in kwargs:
        raise ValueError("deps and targets must both be specified, or neither")

      targets = kwargs["targets"]
      deps = kwargs["deps"]

      if isinstance(targets, (basestring, BuildPath)): targets = targets,
      if isinstance(deps, (basestring, BuildPath)): deps = deps,

      if not all([
          tgt == os.path.splitext("_" + BuildPath.extract(tgt))[1]
          for tgt in targets
      ]):
        raise ValueError("Target format invalid")

      target = BuildTarget()
      targetset = frozenset(targets)

      if targetset in self._targets:
        raise ValueError("Target set already registered.")

      self._targets[targetset] = target

      target.setRule(frozenset(deps), name)

    elif "deps" in kwargs:
      raise ValueError("deps and targets must both be specified, or neither")

    return rule

  def run(self, rootDir, buildDir, *args):
    rootDir = os.path.join(os.getcwd(), rootDir)
    buildDir = os.path.join(rootDir, buildDir)
    buildFile = os.path.join(buildDir, "build.ninja")

    if os.path.exists(buildDir):
      if not os.path.isdir(buildDir):
        raise ValueError("Invalid build directory %s" % (buildDir))
    else:
      os.makedirs(buildDir)

    with open(buildFile, "w") as fs:
      self._emit(fs, rootDir, buildDir)

    ninjaPath = "ninja"

    def testExe(path):
      try:
        with open(os.devnull) as devnull:
          subprocess.call([path, "--version"], stdin = devnull,
                          stdout = devnull, stderr = devnull)

        return True
      except OSError as e:
        if e.errno != os.errno.ENOENT: raise

        return False

    ninjaDir = os.path.join(buildDir, "ninja")
    remCachePath = os.path.join(buildDir, ".bootstrap_head")

    if testExe(ninjaPath):
      if os.path.exists(ninjaDir) and os.path.isdir(ninjaDir):
        print("[Build] Removing extraneous local copy of Ninja.")

        shutil.rmtree(ninjaDir)

      if os.path.exists(remCachePath) and os.path.isfile(remCachePath):
        print("[Build] Removing extraneous cache file.")

        os.remove(remCachePath)

    else:
      print(
          "No installed version of Ninja found.  Looking for a local version..."
      )

      ninjaPath = os.path.join(ninjaDir, "ninja")

      bootstrap = False

      if testExe(ninjaPath):
        print("[Build] Local version found.")

        def unbytes(x):
          if isinstance(x, bytes):
            return str(x.decode('ascii'))

          return x

        subprocess.check_call(["git", "checkout", "master"], cwd = ninjaDir,
                              stdout = subprocess.PIPE,
                              stderr = subprocess.PIPE)

        parseLoc = subprocess.Popen(["git", "rev-parse", "@"], cwd = ninjaDir,
                                    stdout = subprocess.PIPE,
                                    stderr = subprocess.PIPE)
        locOut = str.strip(unbytes(parseLoc.communicate()[0]))

        if (
            os.path.exists(remCachePath) and
            os.path.getmtime(remCachePath) >= time.time() - 86400
        ):
          with open(remCachePath) as fl:
            remOut = str.strip(fl.read())
        else:
          print("[Build] Checking if local Ninja is up-to-date...")

          subprocess.check_call(["git", "fetch"], cwd = ninjaDir)

          parseRem = subprocess.Popen(["git", "rev-parse", r"@{u}"],
                                      cwd = ninjaDir, stdout = subprocess.PIPE)
          remOut = str.strip(unbytes(parseRem.communicate()[0]))

          with open(remCachePath, 'w') as fil:
            fil.write(remOut)

        print("[Build] Local commit: %s; remote commit: %s." % (locOut, remOut))

        if locOut == remOut:
          print("[Build] Local Ninja up-to-date.")
        else:
          print("[Build] Local Ninja out-of-date.  Updating from GitHub...")

          subprocess.check_call(["git", "pull"], cwd = ninjaDir)

          bootstrap = True
      else:
        print(
            "[Build] No local version of Ninja found.  Cloning from GitHub..."
        )

        subprocess.check_call([
            "git", "clone", "git@github.com:ninja-build/ninja.git", ninjaDir
        ])

        bootstrap = True

      if bootstrap:
        print("[Build] Bootstrapping local Ninja...")

        subprocess.check_call([
            sys.executable, os.path.join(ninjaDir, "configure.py"),
            "--bootstrap"
        ], cwd = ninjaDir)

    procinfo = [ninjaPath, "-f", buildFile]
    procinfo.extend(args)

    print(" ".join(procinfo))

    retcode = subprocess.call(procinfo)

    print("[Build] Ninja exited with code %s" % (retcode))

  def path(self, *args):
    return BuildPath(*args)

  def path_b(self, path):
    return self.path(path, False)

  def paths(self, *args):
    return [self.path(arg) for arg in args]

  def paths_b(self, *args):
    return [self.path_b(arg) for arg in args]


class BuildEdge(BuildVarHost):
  def __init__(self, build, targets, deps):
    BuildVarHost.__init__(self)
    self._build = build
    self._targets = frozenset(targets)
    self._deps = deps
    self._rule = None

  def _emit(self, stream, rootDir, buildDir):
    stream.write(
        "build %s: %s " % (self.expandName(rootDir, buildDir), self._getRule())
    )

    self._deps._emit(stream, rootDir, buildDir)

    stream.write("\n")

    self._emitVars(stream, rootDir, buildDir, "  ")

  def expandName(self, rootDir, buildDir):
    return " ".join([
        BuildPath.expand(tgt, rootDir, buildDir) for tgt in self._targets
    ])

  def _getRule(self):
    if self._rule is not None: return self._rule

    targetset = frozenset(
        [os.path.splitext(BuildPath.extract(tgt))[1] for tgt in self._targets]
    )

    if targetset not in self._build._targets:
      raise LookupError(
          "No rule found matching target set %s" % repr(targetset)
      )

    depset = frozenset([
        os.path.splitext(BuildPath.extract(dep))[1] for dep in self._deps._deps
    ])

    return self._build._targets[targetset].getRule(depset)

  def getRule(self):
    name = self._getRule()

    if name is None:
      raise LookupError(
          "No rule found to build %s from %s" %
          (repr(self._targets), repr(self._deps._deps))
      )

    return self._build._rules[name]

  def setRule(self, name):
    self._rule = name
    return self

  def unsetRule(self):
    self._rule = None
    return self


class BuildRule(BuildVarHost):
  def __init__(self, build, name):
    BuildVarHost.__init__(self)
    self._name = name
    self._build = build

  def _emit(self, stream, rootDir, buildDir):
    stream.write("rule %s\n" % (self._name))

    self._emitVars(stream, rootDir, buildDir, "  ")

    return True


class BuildPhonyRule(BuildRule):
  def __init__(self, build):
    BuildRule.__init__(self, build, "phony")

  def _emit(self, stream, rootDir, buildDir):
    return False


class BuildTarget(object):
  def __init__(self):
    self._rules = dict()

  def getRule(self, deps):
    depset = frozenset(deps)

    if depset not in self._rules: return None

    return self._rules[depset]

  def setRule(self, deps, name):
    if name is None:
      raise ValueError("Name cannot be None")

    depset = frozenset(deps)

    if self.getRule(depset) is not None:
      raise ValueError("Dependency set already registered for this target.")

    self._rules[depset] = name
    return self
