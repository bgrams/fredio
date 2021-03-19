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
        cls.event = events.Event("foo")
        cls.loop = utils.loop

    @classmethod
    def tearDownClass(cls):

        # Add a passthrough handler to consumer all lingering events
        # This should be handled by the atexit callback but JIC
        cls.event.add(lambda x: x)
        cls.loop.run_until_complete(events.cancel())
        utils.cancel_running_tasks()

    def setUp(self):
        events._events = dict()

    def assertEvent(self, name: str):
        self.assertIn(name, events._events.keys())
        self.assertIsInstance(events._events[name], events.Event)

    def assertNumRunningTasks(self, num: int):

        # Py36 doesn't seem to clean up cancelled tasks, so only filter for running
        tasks = utils.get_all_tasks()
        running = list(filter(lambda x: not x.done(), tasks))
        self.assertEqual(len(running), num)

    def test_event_add(self):
        self.event.add(lambda x: x)
        self.assertEqual(len(self.event._handlers), 1)

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

        # with self.assertRaises(TypeError):
        #     events.register("foo", lambda x: x)

        self.assertNumRunningTasks(1)


if __name__ == "_main__":
    unittest.main()
