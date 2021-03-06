import os, sys, re, shutil

data = open(sys.argv[1], 'r').read()

if os.path.isdir(sys.argv[2]): shutil.rmtree(sys.argv[2])
os.mkdir(sys.argv[2])

funcs = list(re.split(".*----------------------------------------------------", data))
hex_rays = funcs.pop()
defs = funcs.pop()
decl = funcs.pop()

def parse_arg_split(s):
    out = []
    last = 0
    escape = False
    quote = None
    for i, c in enumerate(s):
        if escape:
            escape = False
            continue
        elif c == '\\':
            escape = True
        if quote:
            if c == quote:
                quote = None
        elif c in ('"', "'"):
                quote = c
        elif c == ',':
            arg = s[last:i].strip()
            out.append(arg)
            last = i + 1
    arg = s[last:]
    if arg:
        out.append(arg)
    return out

def format(data):
    # this is ordered on purpose, so don't change it
    funcs = ['j__objc_msgSend', 'objc_msgSend', 'objc_msgSendSuper', 'objc_msgSendSuper2', 'objc_msgSend_shim', 'objc_msgSend_ptr']
    built = ''

    def my_zip(one, two, filltwo):
        ''' no clue what this is for, sorry! '''
        l = []
        for i in range(max(len(one), len(two))):
            if i >= len(two): l.append((one[i], filltwo))
            elif i >= len(one): l.append(('', two[i]))
            else: l.append((one[i], two[i]))
        return l

    def make_method(parts):
        if len(parts) < 2: return None

        cls = parts[0]
        if cls.find('&OBJC_CLASS___') == 0: cls = cls[14:]
        if cls.startswith('"') and cls.endswith('"'):
            cls = cls.replace('"', '', 1).rsplit('"', 1)[0]

        name = parts[1].strip()
        if not name.startswith('selRef_'):
            return None
        name_parts = name.split('_')[1:]
        if name_parts[-1] == '': name_parts[-1] = None

        args = parts[2:] if len(parts) >= 3 else []

        build = '[%s' % cls
        if len(name_parts) == 1:
            build += ' %s' % name_parts[0]
        else:
            for part, arg in my_zip(name_parts, args, 'nil'):
                if part is not None: build += ' %s:%s' % (part, arg)
        build += ']'

        return build

    data = data.replace('\r\n', '\n')
    for func in funcs:
        while func + '(\n' in data:
            left, right = data.split(func + '(\n', 1)
            end_index = 0
            deep = 1
            for i, c in enumerate(right):
                if c == '(': deep += 1
                if c == ')': deep -= 1
                if deep == 0: break
                end_index += 1
            middle, right = right[:end_index], right[end_index:]
            middle = ' '.join([s.strip() for s in middle.split('\n')])
            data = left + func + '(' + middle + right

    data = re.sub(r'CFSTR\(("[^"]+")\)', r'@\1', data)
    data = data.replace('classRef_', '')

    for line in data.split('\n'):
        used = None
        for func in funcs:
            if func + '(' in line:
                used = func
                break

        index = -1 if used is None else line.find(used)
        if index != -1:
            parts = line[index + len(func) + 1:]

            end_index = 0
            deep = 1
            for i, c in enumerate(parts):
                if c == '(': deep += 1
                if c == ')': deep -= 1
                if deep == 0: break
                end_index += 1

            parts = parts[:end_index]
            parts = parse_arg_split(parts)
            if used in ['objc_msgSendSuper', 'objc_msgSendSuper2']:
                v = parts[0]
                if v.startswith('&'):
                    v = v.replace('&', '', 1)
                parts[0] = '[{} super]'.format(v)

            new = make_method(parts)
            if new is not None:
                line = line[:index] + new + line[index + len(func) + end_index + 2:]

        built = built + line + '\n'

    b = built
    # remove trailing whitespace
    while b[-1] == '\n':
        b = b[:-1]

    l = b.split('\n')
    r = []
    for n in l:
        if n.find('using guessed type') == -1:
            r.append(n)
    return '\n'.join(r)

class Method(object):
    def __init__(self, d):
        d = d[len("// "):]

        self.cls = d[:d.find(" ")]
        d = d[len(self.cls) + len(" "):]

        self.type = d[0] # + for class, - for instance

        d = d[d.find("(") + len(')'):]
        self.ret = d[:d.find(")")]
        d = d[len(self.ret) + len(")"):]

        parts = []
        while len(d) > 0:
            # params or not
            if d.find(")") != -1:
                p = d[:d.find(")")]
                d = d[len(p) + len(")"):]
                if len(d) > 0 and d[0] == ' ': d = d[1:]
            else:
                p = d
                d = d[len(p):]

            if p.find(":") != -1:
                name = p[:p.find(":")]
                p = p[p.find("(") + len("("):]
                arg = p
            else:
                name = p
                arg = None
            if len(name) > 0 and name[0] == ' ': name = name[1:]

            parts.append((name, arg))
        self.parts = parts

    def definition(self):
        r = self.type
        r += " "
        r += '(' + self.ret + ')'

        i = 2
        for name, arg in self.parts:
            if i != 2: r += ' '
            if arg is not None:
                r += name + ":("
                r += arg if arg != "char" else "BOOL"
                r += ")a" + str(i) # match hex-rays
            else:
                r += name
            i += 1

        return r.strip()

    def formatted(self):
        b = format(self.body)
        return b

methods = []
ignored = []

for func in funcs[3:]:
    lines = func.split("\n")
    if len(lines) <= 1:
        ignored.append(func)
        continue

    line = lines[1]
    if line[:2] == '//': # find objc methods
        m = Method(line)
        m.body = '\n'.join(lines[3:]) # ignore first two lines
        methods.append(m)

    ignored.append(func)
    continue

# write out

out = open(sys.argv[2] + "/" + "main.m", 'w')

for block in ignored:
    out.write(format(block) + '\n')

out.write("\n\n")

import itertools

ms = sorted(methods, key=lambda x: x.cls)

for cls, m in itertools.groupby(ms, lambda x: x.cls):
    fn = cls
    if fn.find('(') != -1:
        fn = fn[:fn.find('(')] + '+' + fn[fn.find('(') + len('('):fn.find(')')]

    out = open(sys.argv[2] + "/" + fn + ".m", 'w')

    out.write('#import "' + cls + '.h"\n')
    out.write('\n@implementation ' + cls + '\n')

    for method in m:
        out.write('\n')
        out.write(method.definition())
        out.write(' ')
        out.write(method.formatted())
        out.write('\n')

    out.write('\n@end\n\n')
