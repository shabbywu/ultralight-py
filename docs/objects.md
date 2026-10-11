# Python 对象桥接

Python 创建普通实例后，JS 可以直接访问它的公开属性和方法。list、dict、tuple 也使用实时代理，
不模拟 JS Array/Object。所有操作均在 Python 主线程进行。

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
主框架导航后必须重新绑定；绑定不自动重放。

## 成员与身份

`bind_object(name, instance, *, members=None)` 返回 `PythonBinding`。
默认通过实例字典、slots 和类 MRO 发现公开成员，排除下划线名称。
例如 `members=["value", "increment"]` 可进一步收窄根对象的成员。
嵌套实例仍按默认公开成员规则导出，白名单不递归限制整个对象图。

属性值实时读取，赋值遵循 Python `setattr` 和 property setter。
只读 property、方法及未暴露成员的赋值会报错。未知成员读取返回 JS undefined，
显式 `Python.getattr()` 则抛出 Python AttributeError。
`Object.keys()` 和 `in` 只查询成员名，不执行属性 getter；不自动发现
`__getattr__`、`__dir__` 构造的动态成员，也不支持 JS 修改属性描述符、原型或冻结代理。

每个绑定内部，同一个 Python 对象对应同一代理，支持 `return self`、嵌套别名和循环引用。
不同实例拥有独立的代理及绑定方法缓存，不将实例数据放在 JS 类原型中。
Python 自身共享的类属性仍然共享；桥接不会复制它们。

同一个 Python 实例绑定到两个名称时，两个代理的 `===` 身份不同，但访问同一份 Python 状态。
两个绑定分别撤销。方法参数中的其他代理先恢复成原 Python 对象；返回时按被调用方法所属的
绑定重新导出，因此跨绑定调用不会合并撤销范围。

## Python 容器与运算

```javascript
left.history.append(7);
Python.setitem(left.history, -1, 8);
const last = Python.getitem(left.history, -1);
const count = Python.len(left.history);
Python.delitem(left.history, 0);
const part = Python.getitem(left.history, Python.slice(0, null, 2));
```

方括号不是 Python 索引接口。`values[0]` 不会访问 Python list 的第 0 项；容器的
JS 属性用于暴露 Python 方法。这样可以保持索引类型，并避免 dict 的键与 `get`、`keys`
等方法重名。

```javascript
Python.setitem(options, "keys", 42);
const value = Python.getitem(options, "keys");
const keys = options.keys(); // Python dict_keys 实时视图
for (const key of Python.iter(keys)) {
  console.log(key);
}
```

list/dict 的 `append`、`insert`、`pop`、`update` 等方法直接调用 Python 实现。
负索引、切片、越界、缺失键、不可哈希键和 tuple 只读均遵循 Python 行为。
`Array.isArray(proxy)` 为 false；`Object.keys(dict_proxy)` 枚举 Python 公开成员，
不枚举字典的数据键。数据键使用 `dict_proxy.keys()`。

每个主文档首次桥接时安装只读、不可重新配置的 `Python` 命名空间。
该全局名称保留给桥接；如果页面已经定义同名全局，初始化会报错。

| JS 接口 | 行为 |
| --- | --- |
| `Python.getattr(obj, name)` | 读取允许暴露的属性，遵守绑定白名单 |
| `Python.getitem(obj, key)` | 调用 Python 索引或映射取值 |
| `Python.setitem(obj, key, value)` | 调用 Python 元素赋值 |
| `Python.delitem(obj, key)` | 调用 Python 元素删除 |
| `Python.len(obj)` | Python `len()` |
| `Python.contains(obj, value)` | Python 成员判断；dict 检查键 |
| `Python.slice(stop)` / `slice(start, stop, step)` | 创建 Python slice；null 表示 None |
| `Python.iter(obj)` | Python 迭代器的 JS 适配，支持 `for...of`；结束或提前退出后释放迭代器引用 |
| `Python.call(fn, args, kwargs)` | 调用 Python callable，kwargs 可省略 |
| `Python.to_value(obj)` | 显式复制基础容器为普通 JS Array/Object |

例如传入关键字参数：

```javascript
Python.call(left.increment, [], {amount: 5});
Python.call(values.sort, [], {reverse: true});
```

Python 迭代规则保持不变：例如遍历 dict 时改变其大小会抛 RuntimeError。
Python 异常转成 JS Error，保留异常类型和消息；通过 `view.evaluate()` 调用时表现为
`JavaScriptError`。绑定函数和对象方法返回 awaitable 时转换为 JS Promise，
使用方式见 [Promise 与 asyncio](api.md)。类对象、模块和二进制 buffer 不自动代理。

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
`bind_function()` 使用相同的绑定机制，保留原 callable 身份；回传 Python 时恢复原 callable。
每个绑定强持有已经导出的对象、容器和方法，直到显式解除绑定或文档失效；
不承诺 JS GC 会及时释放它们。

解除绑定后，该绑定中所有已保存的代理、方法和迭代器立即失效，包括 JS 已经保存的
嵌套对象。读取、赋值、调用、枚举和成员判断都会报错。
主框架导航或 View/Runtime 关闭时撤销相关全部绑定，已有 PythonBinding 的 `closed` 变为 true。
函数或属性回调允许解除自身绑定、导航或关闭 View；返回前会检查文档和绑定是否仍然有效。

线程、输入和 Renderer 重入约束沿用 Runtime 的现有规则。Python 引用使用延迟队列释放，
不会在 JSC 的 GC/finalizer 线程中获取 GIL。代理不持有 View 的强引用。
`PythonBinding.closed` 可在其他线程查询；操作与显式关闭仍必须在 Python 主线程进行。

## 按值复制

Python 容器使用实时代理。需要普通 JS Array/Object 时，使用 `Python.to_value()`
复制快照，例如交给 JSON 或 JS 数组算法。复制拒绝循环引用及超过 64 层的数据，
dict 的键必须是字符串，不复制普通 Python 实例或 dict views。

```javascript
const live = get_python_list();
live.append(3);                      // 回写 Python
const snapshot = Python.to_value(live);
snapshot.push(4);                    // 只修改 JS 副本
```

运行示例：

```sh
python examples/objects.py
python examples/tkinter_view.py
python examples/tkinter_view.py --smoke
```
