import asyncio
import inspect
import unittest
from fredio import events
from fredio import utils


class sentinel:

    def __init__(self):
        self.hits = 0

    def touch(self):
        self.hits += 1


class TestEvents(unittest.TestCase):

    event: events.Event
    loop: asyncio.BaseEventLoop

    @classmethod
    def setUpClass(cls):
        cls.loop = utils.loop

    @classmethod
    def tearDownClass(cls):
        print("Cancelling all tasks")
        tasks = utils.get_all_tasks()
        for task in tasks:
            task.cancel()

    def setUp(self):
        self.event = events.Event("foo")
        events._events = dict()

    def assertEvent(self, name: str, test_handlers: bool = True):
        self.assertIn(name, events._events.keys())
        self.assertIsInstance(events._events[name], events.Event)

        if test_handlers:
            handlers = events._events[name].handlers
            for handler in handlers:
                self.assertTrue(inspect.iscoroutinefunction(handler))

    def assertNumTasks(self, num: int):
        tasks = utils.get_all_tasks()
        self.assertEqual(len(tasks), num)

    def test_event_add(self):
        self.event.add(lambda x: x)
        self.assertEqual(len(self.event.handlers), 1)

    def test_event_apply(self):
        _sentinel = sentinel()

        self.event.add(lambda x: _sentinel.touch())
        self.loop.run_until_complete(self.event.apply("bar"))
        self.assertEqual(_sentinel.hits, 1)

    def test_produce(self):
        name = "foo"
        data = "bar"

        async def runtest():
            q = asyncio.Queue()
            await events.produce(name, data, q)
            return await q.get()

        result = self.loop.run_until_complete(runtest())
        self.assertEqual(result, (name, data))

    def test_consume(self):
        async def runtest(_sentinel):
            queue = asyncio.Queue()
            events.register("foo", lambda x: _sentinel.touch())

            await queue.put(("foo", "bar"))
            await events.consume(queue)

        _sentinel = sentinel()
        self.loop.run_until_complete(runtest(_sentinel))
        self.assertEqual(_sentinel.hits, 1)

    def test_register(self):
        events.register("foo", lambda x: x)
        self.assertEvent("foo")

    def test_on_event_deco(self):
        events.on_event("foo")(lambda x: x)

        self.assertEvent("foo")

    def test_listen(self):
        self.assertFalse(events.running())
        self.assertTrue(events.listen())
        self.assertTrue(events.running())
        self.assertNumTasks(1)


if __name__ == "_main__":
    unittest.main()
