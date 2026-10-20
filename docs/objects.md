# Python 对象桥接

Python 创建普通实例后，JS 可以直接访问它的公开属性和方法。Python list/dict 与 JS Array/普通对象
默认通过引用共享，任一侧修改都会在另一侧的下次访问中生效。所有桥接操作均在 Python 主线程进行。

```python
class Counter:
    def __init__(self, value):
        self.value = value
        self.history = []

    def increment(self, amount=1):
        self.value += amount
        self.history.append(self.value)
        return self.value


left, right = Counter(0), Counter(100)
left_binding = view.bind_object("left", left)
right_binding = view.bind_object("right", right)
```

```javascript
left.value = 10;
left.increment(2);
right.increment(3);
const incrementLeft = left.increment;
incrementLeft.call(right, 1); // 仍调用 left：Python 方法已经绑定实例
```

需要在页面内联脚本执行前提供对象时，在主框架 `window_ready` 回调中调用 `bind_object()`。
上述文档级绑定在主框架导航后需要重新创建。需要持续恢复时使用
[独立 API 注册表](appcore.md#注册与恢复)，对象与容器规则相同。

## 成员与身份

`bind_object(name, instance, *, members=None)` 返回 `PythonBinding`。
默认通过实例字典、`__slots__` 和类的方法解析顺序发现公开成员，排除下划线名称。
例如 `members=["value", "increment"]` 可进一步收窄根对象的成员。
嵌套实例仍按默认公开成员规则导出，白名单不递归限制整个对象图。

属性值实时读取，赋值遵循 Python `setattr` 和属性设置器。
只读属性、方法及未暴露成员的赋值会报错。未知成员读取返回 JS undefined，
显式 `Python.getattr()` 则抛出 Python AttributeError。
`Object.keys()` 和 `in` 只查询成员名，不执行属性读取器；不自动发现
`__getattr__`、`__dir__` 构造的动态成员，也不支持 JS 修改属性描述符、原型或冻结代理。

每个绑定内部，同一个 Python 对象对应同一代理，支持 `return self`、嵌套别名和循环引用。
不同实例拥有独立的代理及绑定方法缓存，不将实例数据放在 JS 类原型中。
Python 自身共享的类属性仍然共享；桥接不会复制它们。

同一个 Python 实例绑定到两个名称时，两个代理的 `===` 身份不同，但访问同一份 Python 状态。
两个绑定分别撤销。方法参数中的其他代理先恢复成原 Python 对象；返回时按被调用方法所属的
绑定重新导出，因此跨绑定调用不会合并撤销范围。

## 双向共享容器

Python list 在 JS 中是以真正数组为目标的 Proxy：

```javascript
left.history.push(7);
left.history[0] = 8;
console.log(left.history.length, left.history.at(-1));
console.log(Array.isArray(left.history)); // true
console.log(left.history.map(x => x * 2));
console.log(JSON.stringify(left.history));
```

复用当前 JSC 提供的原生 Array 方法，包括迭代、展开、map/filter/reduce、排序和 splice。
原地修改方法写回原 Python list；map、slice、展开等仍按 JS 规则创建浅副本。
每次访问均同步跨桥接，不承诺原生数组的性能。

Python list 始终稠密。跳跃赋值、扩大 length 时使用 Python `undefined` 哨兵填充；
`delete items[i]` 置为 undefined 并保留长度，删除并移位用 `splice(i, 1)`。
这些位置在 `in`、`Object.keys()`、map 中视为存在，JSON 中输出 null。
负下标使用 `.at(-1)`；`items[-1]` 不表示 Python 负索引。
list 代理不支持额外的字符串或 Symbol 属性写入，也不支持修改描述符、原型或冻结。

Python dict 表现为空原型对象，其属性对应数据键：

```javascript
options.keys = 42;                    // 字符串数据键，不是 Python 方法
Object.assign(options, {enabled: true});
delete options.obsolete;
console.log(Object.keys(options));
console.log(JSON.stringify(options));
```

普通属性读写、in、展开、Object.keys/values/entries 和 JSON 仅覆盖字符串键，包括下划线键。
缺失键读取返回 undefined。整数索引形式的字符串键先按数值排序，其余字符串键按插入顺序枚举。
JS 在调用 Proxy 前已把 `options[1]` 转为 `options["1"]`：两者都访问 Python 字符串键，
不会访问整数键 1。非字符串键通过下面的高级 Python 接口访问，不会自动转字符串。

### 高频读取

实时代理每次读取都会跨越 JS/Python 边界，包括下标、字段和 length。
对大容器只访问少量数据时，可以避免复制整棵对象图；需要反复遍历或计算时，
可在循环前通过 `Python.to_value` 复制所需的子树，再使用原生 JS 容器：

```javascript
const history = Python.to_value(left.history);
const total = history.reduce((sum, value) => sum + value, 0);
```

复制成本取决于数据规模，是否划算还取决于后续访问次数。快照独立于原对象，
不会接收 Python 后续修改，修改快照也不会写回 Python。
实时代理始终读取原对象的当前值，嵌套代理的身份复用不缓存数据、长度或键集合。
性能对比脚本及测量方法见 [开发指南](development.md#容器读取性能基准)。

## JS 容器在 Python 中的视图

```python
items = view.evaluate("globalThis.items = [1, 2]")  # JSArray
items.append(3)
assert view.evaluate("items.length") == 3
view.evaluate("items[0] = 9")
assert items[0] == 9

options = view.evaluate("globalThis.options = {enabled: false}")  # JSObject
options["enabled"] = True
assert view.evaluate("options.enabled") is True
```

`JSArray` 实现 MutableSequence，支持负索引、切片、增删、append/extend、排序等操作；
`JSObject` 实现 MutableMapping，操作 JS 对象的自有可枚举字符串属性，支持 update、get、pop 等。
它们不是内置 list/dict。JS 原生稀疏数组保留空位，Python 读取空位得到 undefined；
Python 删除序列元素会移位。JSObject 的非字符串键访问报 TypeError，缺失键报 KeyError。
读取属性会执行 JS getter，赋值和删除遵循 JS setter、只读属性及可配置性规则。

函数参数、返回值、属性和同步/异步求值统一采用共享语义。嵌套容器按需包装，支持循环引用、
别名和两侧容器混合引用。Python 代理回传时恢复原 Python 对象；JS 容器回传时恢复原 JS 对象，
例如 Python echo 返回传入的 JS 数组时，JS 中 `echo(items) === items` 为 true。
同一文档内，仍存活的同一 JS 容器视图也保持 Python `is` 身份。

视图独立保留 JS 句柄，临时 JSValue 关闭不影响视图。视图支持 close、closed 和 with；
显式关闭会影响持有同一视图的 Python 别名。文档失效或 View/Runtime 关闭后操作报 PageGone。
不同文档之间传递视图报 CrossContext；需要独立数据时显式复制。
JS 容器视图的生命周期不属于传入它的 PythonBinding，但内部保存的 Python 代理仍遵守其绑定撤销范围。

## 高级 Python 运算

常规 JS 容器操作无需 Python 命名空间。需要 Python 键类型、切片、tuple 或关键字参数时，
仍可使用每个文档安装的只读 Python 命名空间；全局名称 Python 仍为桥接保留。

| JS 接口 | 行为 |
| --- | --- |
| `Python.getattr(obj, name)` | 读取允许暴露的 Python 属性，遵守绑定白名单 |
| `Python.getitem/setitem/delitem` | Python 索引、映射键和元素增删，保留键类型 |
| `Python.len(obj)` | Python len；dict 包括非字符串键 |
| `Python.contains(obj, value)` | Python 成员判断；dict 检查键 |
| `Python.slice(stop)` / `slice(start, stop, step)` | 创建 Python slice；null 表示 None |
| `Python.iter(obj)` | Python 迭代器的 JS 适配，支持 for...of |
| `Python.call(fn, args, kwargs)` | Python 调用，支持关键字参数及 awaitable |
| `Python.to_value(obj)` | 显式递归复制基础容器为独立 JS Array/Object |

```javascript
Python.setitem(options, 1, "integer key");
console.log(Python.getitem(options, 1));
Python.call(Python.getattr(left.history, 'sort'), [], {reverse: true});
```

Python 方法不再占据 list/dict 的 JS 属性空间，使用 Python.getattr 访问。
tuple 和其他 Python 对象继续使用既有代理规则。Python 异常保留类型和消息，转换为 JS Error；
通过 view.evaluate 调用时表现为 JavaScriptError。awaitable 转 Promise，类、模块和二进制缓冲区不自动代理。

## 生命周期与撤销

`PythonBinding.close()` 幂等，也可使用上下文管理器。`view.unbind(name)` 解除指定绑定；
不存在的名称无操作。成功重绑同名对象会撤销旧绑定，失败时保留旧绑定。
关闭绑定时，仅删除仍指向该绑定的全局名称，不删除页面后来写入的替代值。

```python
with view.bind_object("temporary", Counter(0)) as binding:
    view.evaluate("temporary.increment()")
assert binding.closed
```

View 持有绑定，丢弃 PythonBinding 句柄不会自动解除绑定。
`bind_function()` 使用相同的绑定机制，保留原可调用对象身份；回传 Python 时恢复原对象。
每个绑定强持有已经导出的对象、容器和方法，直到显式解除绑定或文档失效；
不承诺 JS GC 会及时释放它们。

解除绑定后，该绑定中所有已保存的代理、方法和迭代器立即失效，包括 JS 已经保存的
嵌套对象。读取、赋值、调用、枚举和成员判断都会报错。
主框架导航或 View/Runtime 关闭时撤销相关全部绑定，已有 PythonBinding 的 `closed` 变为 true。
函数或属性回调允许解除自身绑定、导航或关闭 View；返回前会检查文档和绑定是否仍然有效。

线程、输入和 Renderer 重入约束沿用 Runtime 的现有规则。Python 引用使用延迟队列释放，
不会在 JSC 的垃圾回收或终结器线程中获取 GIL。代理不持有 View 的强引用。
`PythonBinding.closed` 可在其他线程查询；操作与显式关闭仍必须在 Python 主线程进行。

## 显式复制与 0.6.0 迁移

0.6.0 将所有可变容器的默认转换改为引用语义。原来依赖普通 JS 容器自动变成 Python
list/dict 的代码，应在数据导出、JSON 编码或脱离文档保存时指定 copy=True：

```python
snapshot = view.evaluate("({items: [1, 2]})", copy=True)
snapshot = await view.evaluate_async("Promise.resolve({items: [1, 2]})", copy=True)
snapshot = await page.evaluate("getData()", copy=True)
snapshot = live.to_python(copy=True)  # JSValue、JSArray、JSObject 均支持
```

copy=True 递归生成独立的 Python list/dict，Python dict 按 JS 可见字符串键投影复制。
共享转换支持循环引用；显式深复制拒绝循环引用和超过 64 层的数据，报 TraversalLimit。
list(live)、dict(live)、JS 展开语法只创建浅副本，嵌套容器仍然共享。
JS 中可直接 JSON.stringify(live)，遵循 JSON 的 undefined、循环引用和 toJSON 规则；
只需独立基础 JS 数据时仍可使用 Python.to_value，其 Python dict 输入必须全部为字符串键。

迁移 list.append → list.push、Python.len(list) → list.length、
Python.getitem(list, -1) → list.at(-1)，以及 Python.to_value(dict) 后取字段 → 直接 dict.field。
不要依赖 items.sort 的 Python reverse 参数；原生 JS sort 接受比较函数，Python 排序可通过高级接口调用。

运行示例：

```sh
python examples/objects.py
python examples/tkinter_view.py
python examples/tkinter_view.py --smoke
```
