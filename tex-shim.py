import os
import shutil
import subprocess
import sys


class FlagInfo(object):
  def __init__(self):
    self.n = None
    self.defaults = None


class Flag(object):
  def __init__(self):
    self.n = None
    self.vals = None

  def __repr__(self):
    if self.vals is not None and self.n is not None:
      raise RuntimeError("Invalid Flag object.")

    return repr(self.n) if self.vals is None else repr(self.vals)


class FlagTracker(object):
  def __init__(self):
    self.flag = None
    self.n = 0

  def add(self, val):
    if self.n > 0: self.n -= 1
    elif self.n == 0: raise RuntimeError("Value limit exceeded.")

    self.flag.vals.append(val)


def main():
  flagDesc = [
      ("output", ["output"], ["o"],
       [None]),
      ("builddir", ["build-dir"], ["b"], [""]),
      ("args", ["args"], ["a"], [""]),
      ("number", ["num"], ["n"], ["1"]),
  ]

  varFlagDesc = [
    ("includes", ["include"], ["I"]),
  ]

  flagInf = dict()
  flagNames = dict()
  sFlagNames = dict()
  flags = dict()
  flagTrk = FlagTracker()
  args = list()
  doFlags = True

  for desc in flagDesc:
    info = flagInf[desc[0]] = FlagInfo()
    flag = flags[desc[0]] = Flag()

    for name in desc[1]:
      flagNames[name] = desc[0]

    for name in desc[2]:
      sFlagNames[name] = desc[0]

    if len(desc) > 3:
      info.n = len(desc[3])
      info.defaults = list(desc[3])
      flag.vals = list()
    else:
      flag.vals = 0

  for desc in varFlagDesc:
    info = flagInf[desc[0]] = FlagInfo()
    flag = flags[desc[0]] = Flag()

    for name in desc[1]:
      flagNames[name] = desc[0]

    for name in desc[2]:
      sFlagNames[name] = desc[0]

    info.n = -1
    flag.vals = list()

  def doFlag(name, flagDict, val = None):
    if flagTrk.n > 0:
      print("Expected value; got flag '%s'" % (name))
      return 1

    if not name in flagDict:
      print("Unknown flag '%s'" % (name))
      return 1

    name = flagDict[name]
    info = flagInf[name]

    if name not in flags:
      raise RuntimeError("Flag key '%s' not found." % (name))

    flag = flags[name]

    if info.n is None:
      if val is not None:
        print("Flag '%s' takes no parameters. (Unexpected '%s')" % (name, val))
        return 1

      info.n += 1
    else:
      flagTrk.flag = flag
      flagTrk.n = 1 if info.n < 0 else info.n

      if val is not None: flagTrk.add(val)

  for arg in sys.argv[1:]:
    if flagTrk.n > 0: flagTrk.add(arg)
    else:
      handled = False

      if doFlags and arg[0] == '-':
        if arg[1] == '-':
          handled = True

          if len(arg) == 2:
            doFlags = False
            continue

          rg = arg[2:]
          eq = rg.find("=")

          if eq >= 0:
            ret = doFlag(rg[:eq], flagNames, rg[eq + 1:])
          else:
            ret = doFlag(rg, flagNames)

          if ret: return ret
        else:
          handled = True

          rg = arg[1:]
          eq = rg.find("=")

          if eq >= 0:
            names = rg[:eq]
            for name in names[:-1]:
              ret = doFlag(name, sFlagNames)

              if ret: return ret

            ret = doFlag(names[-1], sFlagNames, rg[eq + 1:])

            if ret: return ret
          else:
            for name in rg:
              ret = doFlag(rg, sFlagNames)

              if ret: return ret

      if not handled:
        args.append(arg)

  for name in flagInf:
    info = flagInf[name]
    flag = flags[name]

    if info.defaults is not None:
      flag.vals.extend(info.defaults[len(flag.vals):])

  if flagTrk.n > 0:
    print("Missing flag parameters at end.")
    return 1

  print("Flags: %s,\nArgs: %s" % (repr(flags), repr(args)))

  if len(args) < 1:
    print("No executable specified.")
    return 1

  if len(args) < 2:
    print("No input file.")
    return 1

  if flags["output"].vals[0] is None:
    print("No output filename specified.")
    return 1

  try:
    number = int(flags["number"].vals[0])
  except ValueError:
    print("Invalid value for --num flag.")
    return 1

  tname = "ts_tmp"
  while True:
    tmpdir = os.path.join(os.getcwd(), tname)

    try:
      if not os.path.exists(tmpdir):
        os.makedirs(tmpdir)

        break
    except OSError as e:
      print(str(e))

    tname = "_" + tname

  try:
    cwd = os.getcwd()

    infile = os.path.join(
        tmpdir, "%s.tex" %
        (os.path.splitext(os.path.basename(flags["output"].vals[0]))[0])
    )

    tmpoutfile = "%s%s" % (
        os.path.splitext(infile)[0],
        os.path.splitext(flags["output"].vals[0])[1]
    )

    outfile = os.path.join(cwd, flags["output"].vals[0])

    builddir = os.path.join(cwd, flags["builddir"].vals[0])

    os.symlink(os.path.join(cwd, args[1]), infile)

    incs = list()

    for inc in flags["includes"].vals:
      split = inc.split("=", 1)
      frm = split[0]

      if len(split) == 1: to = os.path.basename(frm)
      else: to = split[1]

      frm = os.path.join(cwd, frm)
      to = os.path.join(tmpdir, to)

      incs.append(to)

      print("%s -> %s" % (frm, to))
      os.symlink(frm, to)

    oldwd = cwd
    os.chdir(tmpdir)
    cwd = tmpdir

    try:
      procinf = [args[0]]
      procinf.extend([
          arg for arg in flags["args"].vals[0].split(",") if arg.split() != ""
      ])
      procinf.append(infile)

      print("Process info: %s" % repr(procinf))

      for i in range(number):
        print("Running iteration {}...".format(i + 1))

        proc = subprocess.Popen(procinf, stdin=subprocess.PIPE)
        proc.communicate()

        print("Command exited with code %i" % proc.returncode)

        if proc.returncode: break

      if not proc.returncode:
        shutil.move(tmpoutfile, outfile)

      for inc in incs:
        print("X %s" % inc)
        try: os.unlink(inc)
        except OSError as e: print(str(e))

      if os.path.exists(builddir):
        if not os.path.isdir(builddir):
          print("Invalid build directory '%s'." % (builddir))
          return 1
      else:
        os.makedirs(builddir)

      def cprf(src, dst):
        for fil in os.listdir(src):
          frm = os.path.join(src, fil)
          to = os.path.join(dst, fil)

          if os.path.isdir(frm):
            if os.path.exists(to):
              if os.path.isdir(to): cprf(frm, to)
              else: raise RuntimeError("Unexpected file '%s'" % (to))
          elif os.path.isfile(frm):
            if os.path.exists(to):
              if os.path.isfile(to): os.remove(to)
              else: raise RuntimeError("Unexpected directory '%s'" % (to))

            shutil.copy(frm, to)

      cprf(tmpdir, builddir)

      if proc.returncode: return proc.returncode
    finally:
      os.chdir(oldwd)
  finally:
    try:
      shutil.rmtree(tmpdir)
    except OSError as e:
      print(str(e))

  return 0


sys.exit(main())
