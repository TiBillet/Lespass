function actuArticlesAndAddition(id) {

}

function manageKey(event) {
	const ele = event.target.parentNode
	const articleUuid = ele.dataset.uuid
	const articlePrix = new Big(ele.dataset.prix.replace(',','.'))
	console.log('-> manageKey, articleUuid =', articleUuid, '  --  prix =', articlePrix);
	console.log('type articlePrix =', typeof(articlePrix))
	
}

document.querySelector('#products').addEventListener('click', manageKey)