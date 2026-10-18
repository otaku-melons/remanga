# cards
This extension can parse cards info and download its images. Info stored in descriptive file on `cards` key with following structure.
```JSON
{
	"id": 123,
	"rank": "S",
	"images": [
		{
			"link": "https://remanga.org/media/card-item/image.webp",
			// Resolution requested, but merging between sessions not supported for now.
			"width": null,
			"height": null
		}
	],
	"author": {
		"id": 123456,
		"username": "SomeUser"
	},
	"person": "Person Name"
}
```