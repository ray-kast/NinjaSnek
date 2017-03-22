import configure as conf
import sys


def main():
  build = conf.Build()

  build.set(
      cxx = "clang++",
      cxxflags = " ".join([
          "-fsanitize=address",
          "-g",
          "-D_GLIBCXX_DEBUG",
          "-D_LIBCPP_DEBUG",
          "-DDEBUG",
          "-D_DEBUG",
          "-fcolor-diagnostics",
          "-fno-elide-type",
          "-Ofast",
          "-std=c++14",
          "-Wall",
          "-Wconversion",
          "-Wdeprecated",
          "-Wextra",
          "-Wimplicit",
          "-Winvalid-noreturn",
          "-Wmissing-noreturn",
          "-Wmissing-prototypes",
          "-Wmissing-variable-declarations",
          "-Wnewline-eof",
          "-Wshadow",
          "-Wno-shorten-64-to-32",
          "-Wno-sign-compare",
          "-Wno-sign-conversion",
          "-Wthread-safety",
          "-Wunreachable-code-aggressive",
          "-Wunused",
          "-Werror=old-style-cast",
      ]),
      ldflags = " ".join([
          "-fsanitize=address"
      ]),
      bindir = build.path("bin"),
  )

  build.rule("cxx", targets = (".o"), deps = (".cpp")).set(
      command = "$cxx $cxxflags -MMD -MF $out.d -c $in -o $out",
      deps = "gcc",
      depfile = "$out.d",
  )

  build.rule("link", targets = (""), deps = (".o")).set(
      command = "$cxx $ldflags $in -o $out",
  )

  build.edges(
      (
          "$bindir/overload",
          build.paths_b("main.o", "MurmurHash3.o", "program.o"), True
      ),
      (build.path_b("main.o"), build.path("main.cpp")),
      (build.path_b("MurmurHash3.o"), build.path("MurmurHash3.cpp")),
      (build.path_b("program.o"), build.path("program.cpp")),
  )

  build.run("", "build", *sys.argv[1:])

  return 0


sys.exit(main())
